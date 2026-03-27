"""Physics parameter tools for AMI dataset metadata."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

from ami_mcp.tools._helpers import append_next_actions, run_ami_sync


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
        metadata registered in AMI for an ATLAS MC dataset. Requires an EVNT LDN.

        Note: AMI stores crossSection in nb. This tool converts to pb (x1000)
        for display alongside the raw value.

        Args:
            dataset: Full Logical Dataset Name (LDN), typically an EVNT dataset.
                Example:
                "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
                If you only have a DAOD or other derived LDN, use ami_get_dataset_prov
                first to find the parent EVNT dataset.
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'GetPhysicsParamsForDataset -logicalDatasetName="{dataset}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            if not rows:
                return "No physics parameters found."

            # AMI may return multiple rows with the same keys (one per registered
            # parameter group). Deduplicate: keep first non-empty value per key.
            merged: dict[str, str] = {}
            for row in rows:
                for key, value in row.items():
                    if key not in merged and value not in (None, "", "N/A"):
                        merged[key] = str(value)

            table_rows: list[str] = []
            for key, value in merged.items():
                if key == "crossSection":
                    try:
                        xs_nb = float(value)
                        xs_pb = xs_nb * 1000.0
                        table_rows.append(
                            f"| crossSection | {value} nb ({xs_pb:.6g} pb) |"
                        )
                    except (ValueError, TypeError):
                        table_rows.append(f"| crossSection | {value} |")
                else:
                    table_rows.append(f"| {key} | {value} |")

            if not table_rows:
                return "No physics parameters found."
            lines = [
                "## Physics Parameters",
                "",
                "| Parameter | Value |",
                "| --- | --- |",
                *table_rows,
            ]
            output = "\n".join(lines)
            return append_next_actions(
                output,
                [
                    "Use `ami_lookup_xsec` to cross-check against the official PMG database.",
                    "Use `ami_validate_sample` for automated comparison against the PMG xsec DB.",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
