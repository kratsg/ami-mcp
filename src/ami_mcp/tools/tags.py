"""AMI tag info tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

from ami_mcp.tools._helpers import (
    append_next_actions,
    format_ami_result,
    format_error,
    run_ami_sync,
)


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

        # Accept a full tag chain (e.g. "e8351_s3681_r13144") — look up the first tag
        # and note the remaining ones so the caller can look them up separately.
        first_tag = tag.split("_", maxsplit=1)[0]
        remaining = tag.split("_")[1:]

        command = f'AMIGetAMITagInfo -amiTag="{first_tag}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
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
        return output
