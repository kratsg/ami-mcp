"""PMG hashtag tools for the AMI DatasetWorkbook interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context, FastMCP

from ami_mcp.tools._helpers import format_ami_result, run_ami_sync


def register(mcp: FastMCP) -> None:
    """Register hashtag tools."""

    @mcp.tool()
    async def ami_search_by_hashtags(
        scope: str,
        l1: str,
        l2: str | None = None,
        l3: str | None = None,
        l4: str | None = None,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Find ATLAS MC datasets with a given PMG hashtag combination.

        Uses DatasetWBListDatasetsForHashtag to search for EVNT datasets
        classified under the specified hashtag levels.

        PMG hashtag hierarchy:
          PMGL1  Physics process subgroup (e.g. WeakBoson, Top, Higgs, Diboson)
          PMGL2  Sample type / process (e.g. Vjets, ttbar, WW)
          PMGL3  Usage: Baseline, Systematic, Alternative, Obsolete, Specialised
          PMGL4  Generator detail (e.g. Sherpa_2211, Powheg_Pythia8)

        To list available hashtags at any level, use ami_execute with:
          SearchQuery -catalog="<catalog>" -entity="HASHTAGS"
            -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL1'"

        Args:
            scope: ATLAS campaign scope (e.g. "mc20_13TeV", "mc23_13p6TeV").
            l1: PMGL1 hashtag (required, e.g. "WeakBoson").
            l2: PMGL2 hashtag (optional, e.g. "Vjets").
            l3: PMGL3 hashtag (optional, e.g. "Baseline").
            l4: PMGL4 hashtag (optional).
        """
        client = ctx.request_context.lifespan_context["ami_client"]

        cmd_parts = [
            "DatasetWBListDatasetsForHashtag",
            f'-logicalDatasetName="{scope}.*"',
            f'-PMGL1="{l1}"',
        ]
        if l2:
            cmd_parts.append(f'-PMGL2="{l2}"')
        if l3:
            cmd_parts.append(f'-PMGL3="{l3}"')
        if l4:
            cmd_parts.append(f'-PMGL4="{l4}"')

        command = " ".join(cmd_parts)
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            return format_ami_result(rows)
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

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
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            return format_ami_result(rows)
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
