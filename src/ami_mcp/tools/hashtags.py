"""PMG hashtag tools for the AMI DatasetWorkbook interface."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

from ami_mcp.tools._helpers import append_next_actions, format_error, run_ami_sync


def register(mcp: FastMCP) -> None:
    """Register hashtag tools."""

    @mcp.tool()
    async def ami_search_by_hashtags(
        l1: str,
        l2: str | None = None,
        l3: str | None = None,
        l4: str | None = None,
        scope: str = "mc23_13p6TeV",
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Find ATLAS MC datasets with a given PMG hashtag combination.

        This is the primary way to find MC samples for a physics process.
        Uses DatasetWBListDatasetsForHashtag to search for EVNT datasets
        classified under the specified hashtag levels.

        PMG hashtag hierarchy:
          PMGL1  Physics process subgroup (e.g. WeakBoson, Top, Higgs, Diboson)
          PMGL2  Sample type / process (e.g. Vjets, ttbar, WW)
          PMGL3  Usage: Baseline, Systematic, Alternative, Obsolete, Specialised
          PMGL4  Generator detail (e.g. Sherpa_2211, Powheg_Pythia8)

        To list available hashtags at any level, use ami_execute with:
          SearchQuery -catalog="mc23_001:production" -entity="HASHTAGS"
            -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL1'"

        Args:
            l1: PMGL1 hashtag (required, e.g. "WeakBoson").
            l2: PMGL2 hashtag (optional, e.g. "Vjets").
            l3: PMGL3 hashtag (optional, e.g. "Baseline").
            l4: PMGL4 hashtag (optional).
            scope: ATLAS campaign scope used to filter results client-side
                (e.g. "mc20_13TeV", "mc23_13p6TeV"). Defaults to "mc23_13p6TeV".
                The AMI command returns datasets from all campaigns; this
                prefix-matches the ldn field.
        """
        client = ctx.request_context.lifespan_context["ami_client"]

        scope_levels = ["PMGL1"]
        name_values = [l1]
        if l2:
            scope_levels.append("PMGL2")
            name_values.append(l2)
        if l3:
            scope_levels.append("PMGL3")
            name_values.append(l3)
        if l4:
            scope_levels.append("PMGL4")
            name_values.append(l4)

        command = (
            "DatasetWBListDatasetsForHashtag"
            f' -scope="{",".join(scope_levels)}"'
            f' -name="{",".join(name_values)}"'
            ' -operator="AND"'
        )
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            # Filter to the requested campaign scope client-side
            rows = [r for r in rows if r.get("ldn", "").startswith(f"{scope}.")]
            if not rows:
                return "No results."
            ldns = [r["ldn"] for r in rows]

            lines = [f"## Matching Datasets ({len(ldns)} found)"]
            lines.append(f"**Scope:** {scope}")
            lines.append("")
            lines.append("| DSID | physicsShort | LDN |")
            lines.append("|------|-------------|-----|")

            for ldn in ldns:
                parts = ldn.split(".")
                dsid = parts[1] if len(parts) > 1 else ""
                physics_short = parts[2] if len(parts) > 2 else ""
                lines.append(f"| {dsid} | {physics_short} | `{ldn}` |")

            output = "\n".join(lines)

            return append_next_actions(
                output,
                [
                    "Use `ami_get_dataset_info` on a specific LDN for full metadata.",
                    "Use `ami_get_physics_params` on an EVNT LDN for cross-sections.",
                    "Use `ami_get_dataset_hashtags` on an LDN to confirm its classification.",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Check that the hashtag levels exist in AMI for this scope.",
                    "Use `ami_execute` with -entity=HASHTAGS to list valid names.",
                ],
            )

    @mcp.tool()
    async def ami_get_dataset_hashtags(
        dataset: str,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Get the PMG hashtag classification for a given ATLAS dataset.

        Reverse-looks up the PMGL1-PMGL4 hashtags assigned to a dataset in
        the AMI DatasetWorkbook. Typically used with an EVNT LDN.

        Args:
            dataset: Full Logical Dataset Name (LDN) of the dataset, preferably
                the EVNT dataset. Example:
                "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'DatasetWBListHashtags -ldn="{dataset}"'

        # Warn if the input doesn't look like an EVNT dataset
        prefix = ""
        if ".evgen.EVNT." not in dataset:
            prefix = (
                "*Note: Hashtags are typically registered on EVNT datasets. "
                "If this is a DAOD or AOD, use `ami_get_dataset_prov` to find the "
                "parent EVNT LDN first.*\n\n"
            )

        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            if not rows:
                return "*No hashtags found in AMI.*"
            # Group by scope (AMI returns lowercase keys: 'scope', 'name')
            by_scope: dict[str, list[str]] = {}
            for row in rows:
                scope_val = row.get("scope") or row.get("SCOPE", "?")
                name_val = row.get("name") or row.get("NAME", "?")
                by_scope.setdefault(scope_val, []).append(name_val)
            _none = "\u2014"
            lines = [
                "## PMG Hashtag Classification",
                "",
                "| Level | Tags |",
                "| --- | --- |",
            ]
            for level in ("PMGL1", "PMGL2", "PMGL3", "PMGL4"):
                names = by_scope.get(level, [])
                tag_str = ", ".join(names) if names else _none
                lines.append(f"| {level} | {tag_str} |")
            output = prefix + "\n".join(lines)
            return append_next_actions(
                output,
                [
                    "Use `ami_search_by_hashtags` with these tags to find similar datasets.",
                    "Use `ami_get_physics_params` on this LDN for cross-section data.",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Hashtags are registered on EVNT LDNs (prodStep=evgen, dataType=EVNT).",
                    "Use `ami_get_dataset_prov` to find the EVNT parent of a derived dataset.",
                ],
            )
