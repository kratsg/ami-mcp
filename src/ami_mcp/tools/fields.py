"""AMI entity field-discovery tool."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer  # noqa: TC002
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from ami_mcp.tools._helpers import (
    append_next_actions,
    format_ami_result,
    format_error,
    project_data_type_to_catalog,
)
from ami_mcp.tools._schema import get_entity_fields


class AmiField(BaseModel):
    """One queryable field of an AMI entity."""

    name: str
    type: str
    description: str


class AmiListFieldsResult(BaseModel):
    """Structured result of ``ami_list_fields``."""

    project: str
    catalog: str
    entity: str
    fields: list[AmiField]


def register(mcp: MCPServer) -> None:
    """Register the field-discovery tool."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="List entity fields",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_list_fields(
        project: str,
        data_type: str | None = None,
        entity: str = "dataset",
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiListFieldsResult]:
        """List the field names (with type and description) AMI accepts for an entity.

        These are the valid names for the `fields` argument of
        `ami_list_datasets` and for SELECT/WHERE clauses in `ami_execute`
        SearchQuery MQL. Names are listed in AMI's canonical casing (e.g.
        `datasetNumber`; `dataset_number` is not a field). AMI silently returns
        zero rows for an unknown field rather than an error.

        The catalog is chosen from project and data_type exactly as in
        `ami_list_datasets`.

        Args:
            project: ATLAS project/campaign (e.g. "mc20_13TeV", "mc23_13p6TeV").
            data_type: Data type (e.g. "EVNT", "DAOD_PHYSLITE"); selects the
                catalog, as in ami_list_datasets.
            entity: AMI entity within the catalog (default "dataset").
        """
        catalog = project_data_type_to_catalog(project, data_type)
        try:
            fields = await get_entity_fields(ctx, catalog, entity)
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Verify the project name (e.g. 'mc20_13TeV', 'mc23_13p6TeV').",
                    "Verify the entity exists in the catalog (e.g. 'dataset').",
                ],
            )
        payload = AmiListFieldsResult(
            project=project,
            catalog=catalog,
            entity=entity,
            fields=[AmiField(**vars(f)) for f in fields],
        )
        text = append_next_actions(
            f"Catalog `{catalog}`, entity `{entity}`: {len(fields)} fields.\n\n"
            + format_ami_result([f.model_dump() for f in payload.fields]),
            ["Pass names from `name` as `fields` to `ami_list_datasets`."],
        )
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content=payload.model_dump(mode="json"),
        )
