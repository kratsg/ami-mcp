"""Cached lookup of an AMI entity's field schema, and field-name validation.

AMI answers a query that selects an unknown field with zero rows instead of an
error, so a caller-supplied field name has to be checked against the entity's
real fields before it is sent into MQL.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pyAMI.config
import pyAMI_atlas.api as _atlas_api  # noqa: F401 (side-effect: registers the ATLAS table aliases)

from ami_mcp.tools._helpers import run_ami_command

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

#: Environment variable overriding the schema cache lifetime, in seconds.
SCHEMA_TTL_ENV = "AMI_MCP_SCHEMA_CACHE_TTL_S"

# An entity's schema rarely changes, so a day-long lifetime costs nothing.
_DEFAULT_TTL_S = 24 * 60 * 60

_CLOSE_MATCH_COUNT = 3
_CLOSE_MATCH_CUTOFF = 0.6

# Only bare identifiers are validated; backticked, qualified or computed
# select terms (``COUNT(x)``, ```cat`.`ent`.`f```) are passed through to AMI.
_PLAIN_FIELD = re.compile(r"^\w+$")


@dataclass(frozen=True)
class FieldInfo:
    """One row of an entity's ``Entity_Fields`` rowset."""

    name: str
    type: str
    description: str


def parse_entity_fields(result: Any) -> list[FieldInfo]:
    """Parse the ``Entity_Fields`` rowset of an ``AMIGetEntityInfo`` result.

    Every row is kept: fields with ``showType=0`` are hidden in AMI's UI but
    still queryable.
    """
    return [
        FieldInfo(
            name=row["field"],
            type=row.get("type", ""),
            description=row.get("description", ""),
        )
        for row in result.get_rows("Entity_Fields")
    ]


def _ttl_from_env() -> float:
    return float(os.environ.get(SCHEMA_TTL_ENV, _DEFAULT_TTL_S))


@dataclass
class SchemaCache:
    """Per-(catalog, entity) cache of field schemas with a time-to-live.

    Concurrent lookups of the same key share one AMI fetch (a lock per key,
    re-checked after acquiring it). Failed fetches are never cached.
    """

    ttl_s: float = field(default_factory=_ttl_from_env)
    clock: Callable[[], float] = time.monotonic
    _entries: dict[tuple[str, str], tuple[float, list[FieldInfo]]] = field(
        default_factory=dict
    )
    _locks: dict[tuple[str, str], asyncio.Lock] = field(default_factory=dict)

    def _fresh(self, key: tuple[str, str]) -> list[FieldInfo] | None:
        entry = self._entries.get(key)
        if entry is not None and self.clock() - entry[0] < self.ttl_s:
            return entry[1]
        return None

    async def get(self, ctx: Any, catalog: str, entity: str) -> list[FieldInfo]:
        """Return the fields of *entity* in *catalog*, fetching them if stale."""
        key = (catalog, entity)
        if (cached := self._fresh(key)) is not None:
            return cached
        async with self._locks.setdefault(key, asyncio.Lock()):
            if (cached := self._fresh(key)) is not None:
                return cached
            result = await run_ami_command(
                ctx, f'AMIGetEntityInfo -catalog="{catalog}" -entity="{entity}"'
            )
            fields = parse_entity_fields(result)
            self._entries[key] = (self.clock(), fields)
            return fields

    def clear(self) -> None:
        """Forget every cached schema."""
        self._entries.clear()


_CACHE = SchemaCache()


async def get_entity_fields(ctx: Any, catalog: str, entity: str) -> list[FieldInfo]:
    """Return the cached field schema of *entity* in *catalog*."""
    return await _CACHE.get(ctx, catalog, entity)


def clear_cache() -> None:
    """Empty the process-wide schema cache."""
    _CACHE.clear()


def _dataset_aliases() -> dict[str, str]:
    """Map pyAMI-atlas's snake_case aliases (``dataset_number``) to AMI names."""
    table = pyAMI.config.tables.get("datasets", {})
    return {
        alias: ami_name.split("=", maxsplit=1)[0]
        for alias, ami_name in table.items()
        if not alias.startswith("@")
    }


def find_unknown_fields(
    requested: Sequence[str], fields: Sequence[FieldInfo], entity: str
) -> dict[str, list[str]]:
    """Return each requested name AMI does not know, with suggested real names.

    AMI matches field names case-insensitively, so a name is known if it
    equals any schema field ignoring case. Only names matching nothing get
    suggestions, from the pyAMI-atlas snake_case alias table (dataset entity
    only) and then difflib close matches against the real names and aliases.
    """
    aliases = _dataset_aliases() if entity == "dataset" else {}
    # Keyed by casefolded name; values are the real AMI spelling.
    candidates = {alias.casefold(): ami for alias, ami in aliases.items()}
    candidates |= {f.name.casefold(): f.name for f in fields}
    known = {f.name.casefold() for f in fields}

    unknown: dict[str, list[str]] = {}
    for name in requested:
        folded = name.casefold()
        if folded in known:
            continue
        suggestions: list[str] = []
        for match in [
            folded,
            *difflib.get_close_matches(
                folded,
                list(candidates),
                n=_CLOSE_MATCH_COUNT,
                cutoff=_CLOSE_MATCH_CUTOFF,
            ),
        ]:
            real = candidates.get(match)
            if real and real not in suggestions:
                suggestions.append(real)
        unknown[name] = suggestions[:_CLOSE_MATCH_COUNT]
    return unknown


def canonicalize_fields(fields: str, schema: Sequence[FieldInfo]) -> list[str]:
    """Split a ``fields`` argument, rewriting bare names to the schema's casing.

    AMI echoes the caller's casing in result row keys, so rewriting keeps the
    keys canonical (``datasetNumber``) whatever casing the caller typed.
    Non-bare terms (functions, backticked identifiers) are kept as written.
    """
    canonical = {f.name.casefold(): f.name for f in schema}
    terms = [term.strip() for term in fields.split(",")]
    return [
        canonical.get(term.casefold(), term) if _PLAIN_FIELD.match(term) else term
        for term in terms
        if term
    ]


def split_plain_fields(fields: str) -> list[str]:
    """Split a comma-separated ``fields`` argument into validatable bare names."""
    terms = [term.strip() for term in fields.split(",")]
    return [term for term in terms if _PLAIN_FIELD.match(term)]
