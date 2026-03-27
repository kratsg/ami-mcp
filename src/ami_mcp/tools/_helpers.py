"""Shared helpers for ami-mcp tool implementations."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

_VERTICAL_THRESHOLD = 6


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


# Maps scope strings (e.g. "mc20_13TeV") to their AMI evgen catalog names.
# mc16 and mc20 evgen datasets are stored in the mc15 catalog because they
# were generated with mc15-era job options.
# Source: central-page/new-cp/cli/lib/utils.py scopetag_dict
_SCOPE_TO_CATALOG: dict[str, str] = {
    "mc16_13TeV": "mc15_001:production",
    "mc20_13TeV": "mc15_001:production",
    "mc21_13p6TeV": "mc21_001:production",
    "mc23_13p6TeV": "mc23_001:production",
}


def scope_to_catalog(scope: str) -> str:
    """Map an ATLAS scope string to its AMI evgen catalog name.

    Args:
        scope: ATLAS scope string, e.g. "mc20_13TeV".

    Returns:
        AMI catalog string, e.g. "mc15_001:production".
        Falls back to "<shortscope>_001:production" for unknown scopes.
    """
    if scope in _SCOPE_TO_CATALOG:
        return _SCOPE_TO_CATALOG[scope]
    # Best-effort fallback: take the mc-prefix and assume _001:production
    short = scope.split("_", maxsplit=1)[0]
    return f"{short}_001:production"
