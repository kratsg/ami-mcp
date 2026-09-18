"""Physics parameter tools for AMI dataset metadata."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer  # noqa: TC002
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from ami_mcp.tools._helpers import (
    append_next_actions,
    format_error,
    run_ami_command,
)


class AmiPhysicsParam(BaseModel):
    """One physics parameter value, as registered in AMI."""

    value: str
    units: str = ""


class AmiPhysicsParamsResult(BaseModel):
    """Structured result of ``ami_get_physics_params``."""

    dataset: str
    found: bool
    params: dict[str, AmiPhysicsParam]


def register(mcp: MCPServer) -> None:
    """Register physics parameter tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get physics parameters",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_get_physics_params(
        dataset: str,
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiPhysicsParamsResult]:
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
        command = f'GetPhysicsParamsForDataset -logicalDatasetName="{dataset}"'

        # Warn if the input doesn't look like an EVNT dataset
        prefix = ""
        if ".evgen.EVNT." not in dataset:
            prefix = (
                "*Note: Physics parameters are registered on EVNT datasets. "
                "If this is a DAOD or AOD, use `ami_get_dataset_prov` to find the "
                "parent EVNT LDN first.*\n\n"
            )

        try:
            result = await run_ami_command(ctx, command)
            rows = result.get_rows()
            if not rows:
                return CallToolResult(
                    content=[
                        TextContent(type="text", text="No physics parameters found.")
                    ],
                    structured_content=AmiPhysicsParamsResult(
                        dataset=dataset, found=False, params={}
                    ).model_dump(mode="json"),
                )

            # AMI may return multiple rows with the same keys (one per registered
            # parameter group). Deduplicate: keep first non-empty value per key.
            params: dict[str, tuple[str, str]] = {}
            for row in rows:
                name = row.get("paramName", "")
                value = row.get("paramValue", "")
                units = row.get("units", "")
                if name and value:
                    params[name] = (value, units if units.lower() != "null" else "")

            if not params:
                return CallToolResult(
                    content=[
                        TextContent(type="text", text="No physics parameters found.")
                    ],
                    structured_content=AmiPhysicsParamsResult(
                        dataset=dataset, found=False, params={}
                    ).model_dump(mode="json"),
                )

            # Build table
            table_rows: list[str] = []
            for name, (value, units) in params.items():
                if name == "crossSection":
                    try:
                        xs_nb = float(value)
                        xs_pb = xs_nb * 1000.0
                        table_rows.append(
                            f"| crossSection | {value} {units} ({xs_pb:.6g} pb) |"
                        )
                    except (ValueError, TypeError):
                        table_rows.append(f"| crossSection | {value} {units} |")
                else:
                    table_rows.append(f"| {name} | {value} {units} |")

            if not table_rows:
                return CallToolResult(
                    content=[
                        TextContent(type="text", text="No physics parameters found.")
                    ],
                    structured_content=AmiPhysicsParamsResult(
                        dataset=dataset, found=False, params={}
                    ).model_dump(mode="json"),
                )
            lines = [
                "## Physics Parameters",
                "",
                "| Parameter | Value |",
                "| --- | --- |",
                *table_rows,
            ]
            output = prefix + "\n".join(lines)
            text = append_next_actions(
                output,
                [
                    "Use `ami_lookup_xsec` to cross-check against the official PMG database.",
                    "Use `ami_validate_sample` for automated comparison against the PMG xsec DB.",
                ],
            )
            payload = AmiPhysicsParamsResult(
                dataset=dataset,
                found=True,
                params={
                    name: AmiPhysicsParam(value=value, units=units)
                    for name, (value, units) in params.items()
                },
            )
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=payload.model_dump(mode="json"),
            )
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "This tool requires an EVNT LDN (prodStep=evgen, dataType=EVNT).",
                    "Use `ami_get_dataset_prov` to find the EVNT parent of a DAOD/AOD.",
                ],
            )
