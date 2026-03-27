"""General-purpose AMI command execution tool."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ami_mcp.tools._helpers import format_ami_result, run_ami_sync


def register(mcp: FastMCP) -> None:
    """Register the ami_execute tool."""

    @mcp.tool()
    async def ami_execute(
        command: str,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Execute an arbitrary AMI command string and return the results.

        This is the primary tool for querying AMI. Read the ami://query-language
        resource to learn how to construct command strings. The LLM formulates
        the command string; this tool executes it and returns formatted results.

        Common command patterns:
          SearchQuery -catalog="mc23_001:production" -entity="HASHTAGS"
            -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL1'"

          DatasetWBListDatasetsForHashtag
            -logicalDatasetName="mc20_13TeV.*"
            -PMGL1="WeakBoson" -PMGL2="Vjets" -PMGL3="Baseline"

          AMIGetDatasetInfo -logicalDatasetName="mc20_13TeV.700320.Sh_2211_Zee..."

          GetPhysicsParamsForDataset -logicalDatasetName="..."

        Args:
            command: AMI command string (see ami://query-language resource).
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            return format_ami_result(rows)
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
