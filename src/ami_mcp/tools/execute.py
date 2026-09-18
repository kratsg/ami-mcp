"""General-purpose AMI command execution tool."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer  # noqa: TC002
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from ami_mcp.tools._helpers import (
    check_command_allowed,
    format_ami_result,
    format_error,
    rows_to_dicts,
    run_ami_command,
)


class AmiExecuteResult(BaseModel):
    """Structured result of ``ami_execute``."""

    command: str
    rows: list[dict[str, Any]]
    total: int


def register(mcp: MCPServer) -> None:
    """Register the ami_execute tool."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Execute an AMI command",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_execute(
        command: str,
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiExecuteResult]:
        """Execute an arbitrary AMI command string and return the results.

        Use this when no specialized tool covers your query. Read the
        ami://query-language resource to learn how to construct command strings.
        The LLM formulates the command string; this tool executes it and returns
        formatted results.

        Common command patterns:
          SearchQuery -catalog=mc23_001:production -entity=HASHTAGS
            -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL1'"

          DatasetWBListDatasetsForHashtag
            -scope="PMGL1,PMGL2,PMGL3"
            -name="WeakBoson,Vjets,Baseline"
            -operator="AND"

          AMIGetDatasetInfo -logicalDatasetName="mc20_13TeV.700320.Sh_2211_Zee..."

          GetPhysicsParamsForDataset -logicalDatasetName="..."

        Only allowlisted command verbs are accepted. The built-in set is
        SearchQuery, AMIGetDatasetInfo, AMIGetDatasetProv, AMIGetAMITagInfo,
        GetPhysicsParamsForDataset, DatasetWBListHashtags and
        DatasetWBListDatasetsForHashtag; a deployment may permit more. A
        rejection lists the verbs this server actually permits.

        Args:
            command: AMI command string (see ami://query-language resource).
        """
        if err := check_command_allowed(ctx.request_context.lifespan_context, command):
            return err
        try:
            result = await run_ami_command(ctx, command)
            rows = result.get_rows()
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=["Read the ami://query-language resource for command syntax."],
            )
        text = format_ami_result(rows)
        payload = AmiExecuteResult(
            command=command, rows=rows_to_dicts(rows), total=len(rows)
        )
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content=payload.model_dump(mode="json"),
        )
