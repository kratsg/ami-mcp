"""Shared helpers for ami-mcp tool implementations."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any

from mcp.types import CallToolResult, TextContent

from ami_mcp.policy import (
    DEFAULT_ALLOWED_COMMANDS,
    command_verb,
    describe_allowed,
    is_command_allowed,
)

_log = logging.getLogger(__name__)

_VERTICAL_THRESHOLD = 6

#: Lifespan-context key holding the effective ``ami_execute`` allowlist.
ALLOWED_COMMANDS_KEY = "allowed_commands"

# pyAMI collapses every failure -- transport-layer and AMI-server-side alike --
# into a single pyAMI.exception.Error whose message is 'pyAMI exception: %s'
# (see pyAMI/exception.py and pyAMI/object.py's <error>-element handling).
# There is no exception subclass to catch, so a transient connection failure
# can only be told apart from a semantic AMI error (bad command, invalid
# format, ...) by substring-matching its message. Ugly, but it's what pyAMI
# gives us. Matched case-insensitively against str(exc).
_TRANSIENT_PATTERNS: tuple[str, ...] = (
    "no more data to read from socket",
    "closed connection",
    "connection reset",
    "broken pipe",
    "eof occurred",
    "could not connect to",
    "service temporarily unreachable",
    "timed out",
)

# Number of attempts (including the first) run_ami_command makes by default,
# and the delay between them. Retrying is only safe because every ami-mcp
# tool is a read-only AMI query -- a write tool would need to reason about
# whether a failed attempt already had a side effect before retrying.
_DEFAULT_ATTEMPTS = 2
_DEFAULT_RETRY_DELAY_S = 0.5


def is_transient(exc: Exception) -> bool:
    """Return True if *exc* looks like a transient pyAMI connection failure.

    See the ``_TRANSIENT_PATTERNS`` comment for why this is a substring match
    rather than an exception-type check.
    """
    message = str(exc).lower()
    return any(pattern in message for pattern in _TRANSIENT_PATTERNS)


def format_ami_result(rows: list[Any], max_rows: int = 100) -> str:
    """Format a list of AMI result rows as LLM-friendly markdown.

    Single-row results with many columns are rendered as a vertical
    Field | Value table for readability. Multi-row results use a standard
    horizontal table. Results are truncated at max_rows.

    Args:
        rows: List of OrderedDicts returned by DOMObject.get_rows().
        max_rows: Maximum number of rows to include before truncating.

    Returns:
        Formatted markdown string, or "No results." if rows is empty.
    """
    if not rows:
        return "No results."

    truncated = len(rows) > max_rows
    display = rows[:max_rows]

    if isinstance(display[0], (dict, OrderedDict)):
        keys = list(display[0].keys())
        # Single row with many columns → vertical Field | Value table
        if len(display) == 1 and len(keys) > _VERTICAL_THRESHOLD:
            lines = ["| Field | Value |", "| --- | --- |"]
            lines.extend(f"| {k} | {display[0].get(k, '')} |" for k in keys)
        else:
            header = "| " + " | ".join(keys) + " |"
            separator = "| " + " | ".join("---" for _ in keys) + " |"
            lines = [header, separator]
            lines.extend(
                "| " + " | ".join(str(row.get(k, "")) for k in keys) + " |"
                for row in display
            )
    else:
        lines = [str(r) for r in display]

    if truncated:
        lines.append(f"... ({len(rows) - max_rows} more rows)")

    return "\n".join(lines)


def append_next_actions(output: str, hints: list[str]) -> str:
    """Append a '## Next steps' section to tool output.

    Args:
        output: The formatted tool output.
        hints: List of suggested follow-up actions.

    Returns:
        output unchanged if hints is empty, otherwise output + next steps section.
    """
    if not hints:
        return output
    hint_lines = "\n".join(f"- {h}" for h in hints)
    return f"{output}\n\n---\n**Next steps:**\n{hint_lines}"


_TRANSIENT_HINT = (
    "This looks like a transient AMI connection error; the call was already "
    "retried internally. Try again."
)


def format_error(
    exc: Exception,
    context: str = "",
    hints: list[str] | None = None,
) -> CallToolResult:
    """Format an error as an LLM-facing ``is_error`` result, never raising.

    No ``structured_content`` is set: an error result carries no structured
    payload (mcp SDK's ``convert_result`` only validates ``structured_content``
    against the tool's output model when ``is_error`` is false).

    When *exc* looks like a transient pyAMI connection error (see
    ``is_transient``), a hint saying so is prepended ahead of the caller's own
    hints -- ``run_ami_command`` already retried it once, so this is the point
    where that failure surfaces and the one useful piece of advice ("try
    again") applies to every tool alike, not just the one that happened to
    catch it.

    Args:
        exc: The exception that was raised.
        context: Optional additional context about what failed.
        hints: Optional list of actionable recovery suggestions.

    Returns:
        A ``CallToolResult`` with ``is_error=True`` and the same
        markdown-formatted error prose this helper has always produced.
    """
    all_hints = list(hints) if hints else []
    if is_transient(exc):
        all_hints.insert(0, _TRANSIENT_HINT)
    lines = [f"**Error**: {exc}"]
    if context:
        lines.append(f"\n{context}")
    if all_hints:
        lines.append("\n**Try:**")
        lines.extend(f"- {h}" for h in all_hints)
    text = "\n".join(lines)
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def check_command_allowed(
    lifespan_context: dict[str, Any], command: str
) -> CallToolResult | None:
    """Return an ``is_error`` result if *command*'s verb is not allowlisted, else None.

    Enforced only by ``ami_execute`` -- the other tools build their own fixed
    command strings and must never be blockable by deployment config.

    Falls back to ``DEFAULT_ALLOWED_COMMANDS`` when the lifespan context
    carries no allowlist, so a server built without the policy wiring still
    enforces the documented default set rather than permitting everything.
    """
    allowed = lifespan_context.get(ALLOWED_COMMANDS_KEY) or DEFAULT_ALLOWED_COMMANDS
    if is_command_allowed(command, allowed):
        return None
    verb = command_verb(command)
    msg = (
        f"AMI command verb {verb!r} is not permitted by this server's allowlist."
        if verb
        else "No AMI command was provided."
    )
    return format_error(
        ValueError(msg),
        hints=[
            f"Permitted command verbs: {describe_allowed(allowed)}.",
            "Read the ami://query-language resource for each command's syntax.",
            "Use a specialized ami_* tool if one covers your query.",
        ],
    )


def rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    """Coerce a list of AMI result rows into plain JSON-serializable dicts.

    ``DOMObject.get_rows()`` normally returns a list of ``OrderedDict``, but
    some AMI result shapes are plain values -- this keeps the structured
    payload's schema uniform (a list of objects) either way.

    Args:
        rows: List of rows as returned by ``DOMObject.get_rows()``.

    Returns:
        List of plain ``dict`` objects, one per row.
    """
    return [
        dict(row) if isinstance(row, (dict, OrderedDict)) else {"value": str(row)}
        for row in rows
    ]


async def run_ami_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous pyAMI call in a thread to avoid blocking the event loop.

    pyAMI uses Python's httplib (blocking I/O). This wrapper offloads the call
    to asyncio's thread pool executor so the MCP event loop stays responsive.

    Args:
        func: A callable (e.g. client.execute or pyAMI_atlas.api.get_dataset_info).
        *args: Positional arguments forwarded to func.
        **kwargs: Keyword arguments forwarded to func.

    Returns:
        Whatever func returns.
    """
    return await asyncio.to_thread(func, *args, **kwargs)


async def run_ami_command(
    ctx: Any,
    command: str,
    *,
    format: str = "dom_object",  # pylint: disable=redefined-builtin
    attempts: int = _DEFAULT_ATTEMPTS,
    retry_delay: float = _DEFAULT_RETRY_DELAY_S,
) -> Any:
    """Execute an AMI command with a client scoped to this one call.

    Asks the ``AmiClientFactory`` in the lifespan context for a client, runs
    ``client.execute`` off the event loop, and releases the client (and any
    per-user credential backing it, in broker mode) before returning. Tools
    stay agnostic of how the client is provisioned.

    Transient pyAMI connection errors (see ``is_transient``) are retried up
    to *attempts* times total, invisibly to the caller. This is only safe
    because every ami-mcp tool issues read-only AMI queries -- retrying is
    idempotent. Each attempt re-acquires the client from the factory rather
    than reusing one across attempts: in broker mode, ``get_client()`` redeems
    a fresh per-user VOMS proxy and disposes of it on exit, so a retry that
    reused an already-released client would fail on a dead credential.

    Args:
        ctx: The MCP request Context.
        command: AMI command string.
        format: pyAMI result format (default "dom_object").
        attempts: Total number of attempts before giving up (default 2).
        retry_delay: Seconds to sleep between attempts (default 0.5).

    Returns:
        The pyAMI result object (e.g. DOMObject — call .get_rows() on it).
    """
    factory = ctx.request_context.lifespan_context["client_factory"]

    async def _attempt() -> Any:
        async with factory.get_client(ctx) as client:
            return await run_ami_sync(client.execute, command, format=format)

    for attempt in range(1, attempts):
        try:
            return await _attempt()
        except Exception as exc:  # noqa: PERF203 -- at most one retry by default
            if not is_transient(exc):
                raise
            _log.warning(
                "Transient AMI error on attempt %d/%d, retrying: %s",
                attempt,
                attempts,
                exc,
            )
            await asyncio.sleep(retry_delay)
    return await _attempt()  # final attempt: its exception propagates unwrapped


# Maps scope strings (e.g. "mc20_13TeV") to their AMI catalog names, per
# production step. mc16 and mc20 evgen datasets are stored in the mc15
# catalog (and mc20 sim datasets in the mc16 catalog) because they were
# generated with earlier-campaign job options; reco/derivation datasets live
# in the campaign's own catalog.
# Source: central-page/new-cp/cli/lib/utils.py scopetag_dict
_SCOPE_TO_CATALOG: dict[str, dict[str, str]] = {
    "mc16_13TeV": {
        "evgen": "mc15_001:production",
        "sim": "mc16_001:production",
        "reco": "mc16_001:production",
    },
    "mc20_13TeV": {
        "evgen": "mc15_001:production",
        "sim": "mc16_001:production",
        "reco": "mc20_001:production",
    },
    "mc21_13p6TeV": {
        "evgen": "mc21_001:production",
        "sim": "mc21_001:production",
        "reco": "mc21_001:production",
    },
    "mc23_13p6TeV": {
        "evgen": "mc23_001:production",
        "sim": "mc23_001:production",
        "reco": "mc23_001:production",
    },
}


def data_type_to_prod_step(data_type: str | None) -> str:
    """Map an AMI dataType to the production step whose catalog holds it.

    Args:
        data_type: AMI dataType, e.g. "EVNT", "HITS", "DAOD_PHYS". None (no
            filter given) is treated as "reco" -- a dataset search with no
            data_type is most often looking for a derivation, and ami_execute
            remains available for an evgen-catalog search under full control.

    Returns:
        One of "evgen", "sim", "reco".
    """
    if data_type in ("EVNT", "HEPMC"):
        return "evgen"
    if data_type == "HITS":
        return "sim"
    return "reco"


def scope_to_catalog(scope: str, prod_step: str) -> str:
    """Map an ATLAS scope string and production step to its AMI catalog name.

    Args:
        scope: ATLAS scope string, e.g. "mc20_13TeV".
        prod_step: One of "evgen", "sim", "reco" (see data_type_to_prod_step).

    Returns:
        AMI catalog string, e.g. "mc15_001:production".
        Falls back to "<shortscope>_001:production" for unknown scopes,
        regardless of prod_step.
    """
    if scope in _SCOPE_TO_CATALOG:
        return _SCOPE_TO_CATALOG[scope][prod_step]
    # Best-effort fallback: take the mc-prefix and assume _001:production
    short = scope.split("_", maxsplit=1)[0]
    return f"{short}_001:production"
