"""Server-side policy for which AMI commands ``ami_execute`` may run."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: Command verbs ``ami_execute`` accepts out of the box: exactly the commands
#: documented in the ``ami://query-language`` resource
#: (``ami_mcp.nomenclature.AMI_QUERY_LANGUAGE``), all read-oriented queries.
#: Extend per deployment with ``--allow-command`` / ``AMI_MCP_ALLOW_COMMANDS``;
#: it can never be narrowed below this set.
#:
#: This bounds *which verbs* are reachable through ami_execute, not *what
#: each verb is asked to do* -- SearchQuery accepts a -sql= parameter (raw
#: SQL) alongside -mql=, so an allowlisted SearchQuery can still carry
#: arbitrary SQL to AMI. AMI's own server-side role permissions remain the
#: authority on what that SQL may do; this is not query sanitization.
DEFAULT_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        "SearchQuery",
        "AMIGetDatasetInfo",
        "AMIGetDatasetProv",
        "AMIGetAMITagInfo",
        "GetPhysicsParamsForDataset",
        "DatasetWBListHashtags",
        "DatasetWBListDatasetsForHashtag",
    }
)


def command_verb(command: str) -> str:
    """Return the leading verb of an AMI command string, or "" if there is none.

    Splits on arbitrary whitespace, so leading/trailing spaces and the tabs
    and newlines an LLM leaves in a wrapped command string are all tolerated.
    ``shlex`` is deliberately *not* used: MQL bodies contain single quotes
    (``LIKE '%Zee%'``) and MQL escapes ``'`` as ``''``, so a command can carry
    an odd number of quote characters that ``shlex.split`` raises on instead
    of yielding the verb.
    """
    tokens = command.split(maxsplit=1)
    return tokens[0] if tokens else ""


def parse_allowed_commands(values: Sequence[str] | None) -> frozenset[str]:
    """Split operator-supplied verb lists into individual verbs.

    Accepts a repeated flag (``--allow-command A --allow-command B``) and
    comma- or whitespace-separated values within each occurrence, which is
    what makes a single ``AMI_MCP_ALLOW_COMMANDS=A,B`` env var work too.
    """
    if not values:
        return frozenset()
    return frozenset(
        token for value in values for token in value.replace(",", " ").split()
    )


def resolve_allowed_commands(extra: Sequence[str] | None) -> frozenset[str]:
    """Return the effective allowlist: the built-in defaults plus *extra*.

    Extend-only by construction -- a deployment can widen the allowlist but
    never narrow it below ``DEFAULT_ALLOWED_COMMANDS``.
    """
    return DEFAULT_ALLOWED_COMMANDS | parse_allowed_commands(extra)


def is_command_allowed(command: str, allowed: Iterable[str]) -> bool:
    """Return True if *command*'s leading verb is in *allowed*.

    Matching is case-insensitive: case cannot smuggle a *different* verb past
    the gate, so insensitivity costs nothing and avoids rejecting a model that
    typed ``searchQuery``.
    """
    verb = command_verb(command)
    if not verb:
        return False
    return verb.casefold() in {entry.casefold() for entry in allowed}


def describe_allowed(allowed: Iterable[str]) -> str:
    """Return a stable, comma-separated rendering of *allowed* for error text."""
    return ", ".join(sorted(allowed))
