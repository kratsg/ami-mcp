"""AMI tag info tools."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer  # noqa: TC002
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from ami_mcp.tools._helpers import (
    append_next_actions,
    format_ami_result,
    format_error,
    rows_to_dicts,
    run_ami_command,
)


class AmiTagInfoResult(BaseModel):
    """Structured result of ``ami_get_ami_tag``."""

    tag: str
    first_tag: str
    remaining_tags: list[str]
    rows: list[dict[str, Any]]


def register(mcp: MCPServer) -> None:
    """Register AMI tag info tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get AMI tag info",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_get_ami_tag(
        tag: str,
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiTagInfoResult]:
        """Get information about an AMI processing tag.

        AMI tags record the configuration of each processing step. Tag letters:
          e=evgen  s=simul  d=digit  r=reco  p=deriv  m=merge

        Args:
            tag: AMI tag string, e.g. "e8351", "s3681", "p5855".
        """
        # Accept a full tag chain (e.g. "e8351_s3681_r13144") — look up the first tag
        # and note the remaining ones so the caller can look them up separately.
        first_tag = tag.split("_", maxsplit=1)[0]
        remaining = tag.split("_")[1:]

        command = f'AMIGetAMITagInfo -amiTag="{first_tag}"'
        try:
            result = await run_ami_command(ctx, command)
            rows = result.get_rows("amiTagInfo")
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Tag format: single tag like 'e8351', 's3681', or 'p5855'.",
                    "Tag letters: e=evgen  s=simul  d=digit  r=reco  p=deriv  m=merge",
                ],
            )
        output = format_ami_result(rows)
        if rows:
            hints = [
                "Use `ami_get_dataset_info` on a dataset with this tag for its metadata.",
                "Use `ami_get_dataset_prov` to see all datasets in a processing chain.",
            ]
            if remaining:
                remaining_str = ", ".join(f"`{t}`" for t in remaining)
                hints.append(
                    f"To look up remaining tags in this chain, call separately with: {remaining_str}"
                )
            output = append_next_actions(output, hints)
        payload = AmiTagInfoResult(
            tag=tag,
            first_tag=first_tag,
            remaining_tags=remaining,
            rows=rows_to_dicts(rows),
        )
        return CallToolResult(
            content=[TextContent(type="text", text=output)],
            structured_content=payload.model_dump(mode="json"),
        )
