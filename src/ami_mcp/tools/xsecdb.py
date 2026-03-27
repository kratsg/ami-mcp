"""PMG cross-section database tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

_DEFAULT_PMGXSEC_PATH = "/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools"


def _get_xsec_path() -> Path:
    """Return the configured PMGxsecDB directory path."""
    return Path(os.environ.get("ATLAS_PMGXSEC_PATH", _DEFAULT_PMGXSEC_PATH))


def _parse_header(header_line: str) -> list[str]:
    """Parse a PMGxsecDB header line into column names.

    Header format: colName/TYPE:colName/TYPE:...
    Returns just the column names (without /TYPE suffixes).
    """
    return [col.split("/")[0] for col in header_line.strip().split(":")]


def _parse_db_file(db_path: Path, dsid: int, etag: str | None) -> list[dict[str, str]]:
    """Parse a PMGxsecDB file and return matching rows.

    Args:
        db_path: Path to the PMGxsecDB_*.txt file.
        dsid: Dataset number to filter on.
        etag: Optional evgen AMI tag to filter on (e.g. "e8351").

    Returns:
        List of matching row dicts with column names as keys.
    """
    with db_path.open(encoding="utf-8") as fh:
        lines = fh.readlines()

    if not lines:
        return []

    columns = _parse_header(lines[0])
    dsid_str = str(dsid)

    # Find the dataset_number column index
    try:
        dsid_col = columns.index("dataset_number")
    except ValueError:
        # Fallback: first column
        dsid_col = 0

    etag_col: int | None = None
    if "etag" in columns:
        etag_col = columns.index("etag")

    results: list[dict[str, str]] = []
    for raw_line in lines[1:]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [p for p in stripped.split("\t") if p]
        if len(parts) < len(columns):
            # Pad short rows
            parts += [""] * (len(columns) - len(parts))
        if parts[dsid_col] != dsid_str:
            continue
        if etag is not None and etag_col is not None and parts[etag_col] != etag:
            continue
        results.append(dict(zip(columns, parts, strict=False)))

    return results


def _format_xsec_rows(rows: list[dict[str, str]]) -> str:
    """Format xsec DB rows as markdown tables, converting units where needed."""
    if not rows:
        return "No matching entries found."

    sections: list[str] = []
    for i, row in enumerate(rows):
        entry_lines: list[str] = []
        if len(rows) > 1:
            entry_lines.append(f"## Entry {i + 1}")
            entry_lines.append("")
        entry_lines.append("| Field | Value |")
        entry_lines.append("| --- | --- |")
        for key, value in row.items():
            if not value:
                continue
            # Normalise cross-section to pb for display
            if key == "crossSection_pb":
                entry_lines.append(f"| crossSection | {value} pb |")
            elif key == "crossSection":
                # Older files store in nb; convert to pb
                try:
                    xs_pb = float(value) * 1000.0
                    entry_lines.append(
                        f"| crossSection | {value} nb ({xs_pb:.6g} pb) |"
                    )
                except (ValueError, TypeError):
                    entry_lines.append(f"| crossSection | {value} (nb) |")
            else:
                entry_lines.append(f"| {key} | {value} |")
        sections.append("\n".join(entry_lines))
    return "\n\n".join(sections)


def register(mcp: FastMCP) -> None:
    """Register PMG cross-section database tools."""

    @mcp.tool()
    async def ami_list_xsec_databases(  # pylint: disable=unused-argument
        *,
        ctx: Context[Any, Any],  # noqa: ARG001
    ) -> str:
        """List available PMG cross-section database files.

        Scans the ATLAS_PMGXSEC_PATH directory (default:
        /cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools)
        for PMGxsecDB_*.txt files.

        Returns each file's name and the campaign it covers.
        """
        xsec_path = _get_xsec_path()
        if not xsec_path.is_dir():
            return (
                f"Error: ATLAS_PMGXSEC_PATH={xsec_path!r} does not exist or "
                "is not a directory. Set ATLAS_PMGXSEC_PATH to the directory "
                "containing PMGxsecDB_*.txt files."
            )

        db_files = sorted(xsec_path.glob("PMGxsecDB*.txt"))
        if not db_files:
            return f"No PMGxsecDB*.txt files found in {xsec_path}"

        lines = [
            "## PMG Cross-Section Databases",
            "",
            f"Path: `{xsec_path}`",
            "",
            "| File | Campaign |",
            "| --- | --- |",
        ]
        for f in db_files:
            # Extract campaign name from filename: PMGxsecDB_mc16.txt -> mc16
            stem = f.stem  # e.g. PMGxsecDB_mc16
            campaign = stem.replace("PMGxsecDB_", "").replace("PMGxsecDB", "")
            lines.append(f"| {f.name} | {campaign or 'unknown'} |")

        return "\n".join(lines)

    @mcp.tool()
    async def ami_lookup_xsec(  # pylint: disable=unused-argument
        dsid: int,
        database: str | None = None,
        etag: str | None = None,
        *,
        ctx: Context[Any, Any],  # noqa: ARG001
    ) -> str:
        """Look up cross-section, filter efficiency, and k-factor for a DSID.

        Use this to get the official PMG cross-section for a DSID. More
        authoritative than AMI physics params for analysis use.

        Reads the specified PMG cross-section database file and returns the
        matching entry (or all entries if no etag is given and multiple exist).
        If database is omitted, all available DB files are searched and all
        matching entries are returned with the source file annotated.

        Args:
            dsid: Dataset number (DSID), e.g. 700320.
            database: Database file name or campaign shorthand.
                Accepts the full filename (e.g. "PMGxsecDB_mc23.txt") or
                just the campaign part (e.g. "mc23" or "mc16").
                If omitted, all available databases are searched.
            etag: Optional evgen AMI tag to select a specific entry when a DSID
                has multiple rows (e.g. "e8351"). If None, all rows are returned.
        """
        xsec_path = _get_xsec_path()

        _next_hints = [
            "Use `ami_get_physics_params` to compare with AMI-registered values.",
            "Use `ami_validate_sample` for automated cross-check against AMI.",
        ]

        if database is None:
            # Search all available DB files
            db_files = sorted(xsec_path.glob("PMGxsecDB*.txt"))
            if not db_files:
                return f"No PMGxsecDB*.txt files found in {xsec_path}"
            all_sections: list[str] = []
            for each_db in db_files:
                try:
                    rows = _parse_db_file(each_db, dsid, etag)
                    if rows:
                        formatted = _format_xsec_rows(rows)
                        all_sections.append(f"### {each_db.name}\n\n{formatted}")
                except Exception:  # noqa: BLE001, PERF203
                    continue
            if not all_sections:
                return f"No matching entries found for DSID {dsid} in any database."
            body = "\n\n".join(all_sections)
            return f"{body}\n\n---\n**Next steps:**\n" + "\n".join(
                f"- {h}" for h in _next_hints
            )

        # Resolve named_db from the database argument
        if database.endswith(".txt"):
            named_db: Path = xsec_path / database
        else:
            # Treat as campaign name: mc23 -> PMGxsecDB_mc23.txt
            named_db = xsec_path / f"PMGxsecDB_{database}.txt"

        if not named_db.exists():
            available = sorted(xsec_path.glob("PMGxsecDB*.txt"))
            names = ", ".join(f.name for f in available) if available else "none"
            return (
                f"Error: database file {named_db.name!r} not found in {xsec_path}.\n"
                f"Available files: {names}"
            )

        try:
            rows = _parse_db_file(named_db, dsid, etag)
        except Exception as exc:  # noqa: BLE001
            return f"Error reading {named_db.name}: {exc}"
        result = _format_xsec_rows(rows)
        if rows:
            return f"{result}\n\n---\n**Next steps:**\n" + "\n".join(
                f"- {h}" for h in _next_hints
            )
        return result
