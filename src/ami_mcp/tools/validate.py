"""Validation tools for ATLAS MC samples."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

from ami_mcp.tools._helpers import run_ami_sync
from ami_mcp.tools.xsecdb import _get_xsec_path, _parse_db_file

if TYPE_CHECKING:
    from pathlib import Path

_XSEC_COMPARE_FIELDS = [
    ("crossSection", "crossSection_pb", 1000.0, "crossSection"),
    ("crossSection", "crossSection", 1.0, "crossSection"),
    ("genFiltEff", "genFiltEff", 1.0, "genFiltEff"),
    ("kFactor", "kFactor", 1.0, "kFactor"),
]


def _compare_xsec_row(
    section_lines: list[str],
    db_row: dict[str, str],
    ami_params: dict[str, str],
) -> None:
    """Append OK/WARNING bullet lines comparing AMI params against one DB row."""
    for ami_key, db_key, unit_factor, label in _XSEC_COMPARE_FIELDS:
        if db_key not in db_row:
            continue
        ami_val_str = ami_params.get(ami_key, "")
        db_val_str = db_row.get(db_key, "")
        if not ami_val_str or not db_val_str:
            continue
        try:
            ami_val = float(ami_val_str) * unit_factor
            db_val = float(db_val_str)
            if abs(ami_val - db_val) > 1e-6 * max(abs(db_val), 1.0):
                section_lines.append(
                    f"- **WARNING**: AMI {label}={ami_val:.6g} != DB {label}={db_val:.6g}"
                )
            else:
                section_lines.append(f"- **OK**: {label}={db_val:.6g} (matches DB)")
        except (ValueError, TypeError):
            pass


def _xsec_db_section(
    section_lines: list[str],
    ldn: str,
    database: str,
    ami_params: dict[str, str],
) -> None:
    """Append cross-section DB comparison lines to section_lines."""
    xsec_path = _get_xsec_path()
    db_file: Path = (
        xsec_path / database
        if database.endswith(".txt")
        else xsec_path / f"PMGxsecDB_{database}.txt"
    )

    if not db_file.exists():
        section_lines.append(
            f"*xsec DB: file {db_file.name!r} not found — skipping comparison*"
        )
        return

    parts = ldn.split(".")
    dsid: int | None = None
    etag: str | None = None
    with contextlib.suppress(ValueError, IndexError):
        dsid = int(parts[1]) if len(parts) > 1 else None
    if len(parts) > 5:
        for tag_part in parts[-1].split("_"):
            if tag_part.startswith("e") and tag_part[1:].isdigit():
                etag = tag_part
                break

    if dsid is None:
        section_lines.append("*xsec DB: could not extract DSID from LDN*")
        return

    try:
        db_rows = _parse_db_file(db_file, dsid, etag)
        if not db_rows:
            section_lines.append(
                f"*xsec DB: DSID {dsid}"
                + (f" etag {etag}" if etag else "")
                + " not found in DB*"
            )
        else:
            section_lines.append("### Cross-Section Comparison")
            section_lines.append("")
            _compare_xsec_row(section_lines, db_rows[0], ami_params)
            section_lines.append("")
    except Exception as exc:  # noqa: BLE001
        section_lines.append(f"*xsec DB comparison error: {exc}*")


def register(mcp: FastMCP) -> None:
    """Register validation tools."""

    @mcp.tool()
    async def ami_validate_sample(
        datasets: str,
        database: str | None = None,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Validate ATLAS MC samples: check hashtag classification and metadata.

        For each dataset LDN provided:
          1. Looks up PMG hashtag classification (PMGL1-PMGL4) in AMI.
          2. If a cross-section database is specified, compares the AMI physics
             parameters (crossSection, genFiltEff, kFactor) against the PMG
             xsec DB values and flags discrepancies.

        Args:
            datasets: One or more Logical Dataset Names (LDNs), one per line.
                Typically EVNT datasets. Example:
                "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
            database: Optional PMG xsec DB file or campaign (e.g. "mc16", "mc23").
                If provided, cross-section metadata is compared against the DB.
        """
        client = ctx.request_context.lifespan_context["ami_client"]

        ldn_list = [ln.strip() for ln in datasets.splitlines() if ln.strip()]
        if not ldn_list:
            return "Error: no dataset LDNs provided."

        output_sections: list[str] = []

        for ldn in ldn_list:
            section_lines = [f"## {ldn}", ""]

            # --- Hashtag lookup ---
            try:
                hashtag_result = await run_ami_sync(
                    client.execute,
                    f'DatasetWBListHashtags -ldn="{ldn}"',
                    format="dom_object",
                )
                hashtag_rows = hashtag_result.get_rows()
                if hashtag_rows:
                    by_scope: dict[str, list[str]] = {}
                    for row in hashtag_rows:
                        scope = row.get("SCOPE", "?")
                        name = row.get("NAME", "?")
                        by_scope.setdefault(scope, []).append(name)
                    section_lines.append("### Hashtags")
                    section_lines.append("")
                    section_lines.append("| Level | Tags |")
                    section_lines.append("| --- | --- |")
                    _none = "\u2014"
                    for level in ("PMGL1", "PMGL2", "PMGL3", "PMGL4"):
                        names = by_scope.get(level, [])
                        tag_str = ", ".join(names) if names else _none
                        section_lines.append(f"| {level} | {tag_str} |")
                    section_lines.append("")
                else:
                    section_lines.append("*No hashtags found in AMI.*")
                    section_lines.append("")
            except Exception as exc:  # noqa: BLE001
                section_lines.append(f"*Hashtag lookup error: {exc}*")
                section_lines.append("")

            # --- Physics params from AMI ---
            ami_params: dict[str, str] = {}
            try:
                phys_result = await run_ami_sync(
                    client.execute,
                    f'GetPhysicsParamsForDataset -logicalDatasetName="{ldn}"',
                    format="dom_object",
                )
                phys_rows = phys_result.get_rows()
                if phys_rows:
                    ami_params = dict(phys_rows[0])
            except Exception as exc:  # noqa: BLE001
                section_lines.append(f"*Physics params lookup error: {exc}*")
                section_lines.append("")

            # --- Cross-section DB comparison ---
            if database is not None and ami_params:
                _xsec_db_section(section_lines, ldn, database, ami_params)

            output_sections.append("\n".join(section_lines))

        return "\n\n".join(output_sections)
