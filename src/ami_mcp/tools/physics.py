"""Physics parameter tools for AMI dataset metadata."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

from ami_mcp.tools._helpers import run_ami_sync


def register(mcp: FastMCP) -> None:
    """Register physics parameter tools."""

    @mcp.tool()
    async def ami_get_physics_params(
        dataset: str,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Get physics parameters (cross-section, filter efficiency, k-factor) for a dataset.

        Uses GetPhysicsParamsForDataset to retrieve the generator-level physics
        metadata registered in AMI for an ATLAS MC dataset.

        Note: AMI stores crossSection in nb. This tool converts to pb (x1000)
        for display alongside the raw value.

        Args:
            dataset: Full Logical Dataset Name (LDN), typically an EVNT dataset.
                Example:
                "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'GetPhysicsParamsForDataset -logicalDatasetName="{dataset}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            if not rows:
                return "No physics parameters found."

            lines: list[str] = []
            for row in rows:
                for key, value in row.items():
                    if key == "crossSection" and value not in (None, "", "N/A"):
                        try:
                            xs_nb = float(value)
                            xs_pb = xs_nb * 1000.0
                            lines.append(f"crossSection: {value} nb  ({xs_pb:.6g} pb)")
                        except (ValueError, TypeError):
                            lines.append(f"crossSection: {value}")
                    elif value is not None and value != "":
                        lines.append(f"{key}: {value}")
            return "\n".join(lines) if lines else "No physics parameters found."
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
