"""AMI tag info tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ami_mcp.tools._helpers import format_ami_result, run_ami_sync


def register(mcp: FastMCP) -> None:
    """Register AMI tag info tools."""

    @mcp.tool()
    async def ami_get_ami_tag(
        tag: str,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Get information about an AMI processing tag.

        AMI tags record the configuration of each processing step. Tag letters:
          e=evgen  s=simul  d=digit  r=reco  p=deriv  m=merge

        Args:
            tag: AMI tag string, e.g. "e8351", "s3681", "p5855".
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'AMIGetAMITagInfo -amiTag="{tag}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows("amiTagInfo")
            return format_ami_result(rows)
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
