"""AMI dataset info tools."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer  # noqa: TC002
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from ami_mcp.tools._helpers import (
    append_next_actions,
    data_type_to_prod_step,
    format_ami_result,
    format_error,
    rows_to_dicts,
    run_ami_command,
    scope_to_catalog,
)

_DATASET_INFO_FIELDS = [
    "logicalDatasetName",
    "datasetNumber",
    "physicsShort",
    "nFiles",
    "totalEvents",
    "totalSize",
    "crossSection",
    "genFiltEff",
    "amiStatus",
    "prodsysStatus",
    "dataType",
    "productionStep",
    "projectName",
    "version",
]


class AmiDatasetInfoResult(BaseModel):
    """Structured result of ``ami_get_dataset_info``."""

    dataset: str
    found: bool
    fields: dict[str, str]


class AmiDatasetProvResult(BaseModel):
    """Structured result of ``ami_get_dataset_prov``."""

    dataset: str
    found: bool
    summary: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class AmiListDatasetsResult(BaseModel):
    """Structured result of ``ami_list_datasets``."""

    patterns: str
    project: str
    catalog: str
    ami_status: str | None
    rows: list[dict[str, Any]]
    total: int


def register(mcp: MCPServer) -> None:
    """Register dataset info tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get dataset info",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_get_dataset_info(
        dataset: str,
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiDatasetInfoResult]:
        """Get metadata for an ATLAS dataset (LDN) from AMI.

        Returns key fields: nFiles, totalEvents, totalSize, crossSection, genFiltEff,
        amiStatus, and related metadata registered in AMI for this dataset.
        Use ami_execute with AMIGetDatasetInfo for all raw fields.

        Args:
            dataset: Full Logical Dataset Name (LDN), e.g.
                "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.deriv.DAOD_PHYS.e8351_s3681_r13144_r13146_p5855"
        """
        command = f'AMIGetDatasetInfo -logicalDatasetName="{dataset}"'
        try:
            result = await run_ami_command(ctx, command)
            rows = result.get_rows()
            if not rows:
                return CallToolResult(
                    content=[TextContent(type="text", text="No results.")],
                    structured_content=AmiDatasetInfoResult(
                        dataset=dataset, found=False, fields={}
                    ).model_dump(mode="json"),
                )
            # Filter to curated fields; fall back to all fields if none match
            row = rows[0]
            filtered = {k: v for k, v in row.items() if k in _DATASET_INFO_FIELDS}
            display_rows = [filtered] if filtered else rows
            output = format_ami_result(display_rows)

            hints = [
                "Use `ami_get_dataset_prov` to trace the processing chain (EVNT→HITS→AOD→DAOD).",
                "Use `ami_get_physics_params` on the EVNT LDN for cross-section details.",
                "Use `ami_get_dataset_hashtags` on an EVNT LDN for PMG classification.",
            ]
            # Contextual hints based on dataset status
            ami_status = filtered.get("amiStatus", "")
            n_files = filtered.get("nFiles", "")
            if ami_status in ("TRASHED", "INVALID"):
                hints.insert(
                    0,
                    f"This dataset is {ami_status}. Use `ami_list_datasets` to find a newer version.",
                )
            elif n_files == "0":
                hints.insert(
                    0,
                    "nFiles=0: dataset may be deleted or not yet produced. Check prodsysStatus.",
                )

            text = append_next_actions(output, hints)
            payload = AmiDatasetInfoResult(
                dataset=dataset,
                found=True,
                fields={k: str(v) for k, v in (filtered or dict(row)).items()},
            )
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=payload.model_dump(mode="json"),
            )
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Verify the LDN is complete: project.DSID.physicsShort.prodStep.dataType.tags",
                    "Use `ami_list_datasets` to search by physicsShort pattern.",
                ],
            )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get dataset provenance",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_get_dataset_prov(
        dataset: str,
        data_types: str | None = "EVNT,HITS,RDO,ESD,AOD,HEPMC,DAOD_",
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiDatasetProvResult]:
        """Get the provenance (parent/child chain) for an ATLAS dataset.

        Use this to trace a DAOD back to its EVNT, or to find derived datasets
        from an EVNT. Returns node and edge information showing the dataset's
        processing lineage (e.g., EVNT → HITS → RDO → AOD → DAOD).

        The output includes:
          - **Lineage Summary**: a compact chain of data types, grouped by
            processing distance. Nodes at the same distance are shown in
            parentheses. This provides a high-level view of the dataset's
            lineage, e.g., which datasets are produced in parallel at a
            given processing step.
          - **Nodes**: table of individual datasets including:
              - logicalDatasetName
              - dataType
              - distance (steps away from the input dataset)
              - event count
          - **Edges**: optional connections between datasets that show parent-child
            relationships, only between surviving nodes after filtering.

        **Note**: Server-side filtering by data type is not supported. Filtering
        happens after retrieving all lineage nodes, so this command may take
        longer for datasets with extensive provenance chains.

        Args:
            dataset: Full Logical Dataset Name (LDN).
            data_types: Filter by data types, comma-separated (e.g. "EVNT,AOD,DAOD_PHYS").
                Defaults to physics-relevant types and excludes LOG/TXT noise.
                Prefix matching is supported (e.g. "DAOD_" keeps all DAOD_*).

        Returns:
            Formatted string with lineage summary, node table, and optional edges.
        """
        command = f'AMIGetDatasetProv -logicalDatasetName="{dataset}"'

        try:
            result = await run_ami_command(ctx, command)
            nodes = result.get_rows("node")
            edges = result.get_rows("edge")

            if not nodes:
                return CallToolResult(
                    content=[TextContent(type="text", text="No provenance found.")],
                    structured_content=AmiDatasetProvResult(
                        dataset=dataset, found=False, summary="", nodes=[], edges=[]
                    ).model_dump(mode="json"),
                )

            # ------------------------------------------------------------
            # 1. Parse data_types filter
            # ------------------------------------------------------------
            allowed_exact: set[str] = set()
            allowed_prefix: list[str] = []

            if data_types:
                for dt in [d.strip() for d in data_types.split(",") if d.strip()]:
                    if dt.endswith("_"):
                        allowed_prefix.append(dt)
                    else:
                        allowed_exact.add(dt)

            def keep_type(dt: str | None) -> bool:
                if not dt:
                    return False
                if dt in allowed_exact:
                    return True
                return any(dt.startswith(p) for p in allowed_prefix)

            # ------------------------------------------------------------
            # 2. Filter nodes
            # ------------------------------------------------------------
            filtered_nodes = [n for n in nodes if keep_type(n.get("dataType"))]
            if not filtered_nodes:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text", text="No nodes remain after filtering."
                        )
                    ],
                    structured_content=AmiDatasetProvResult(
                        dataset=dataset, found=False, summary="", nodes=[], edges=[]
                    ).model_dump(mode="json"),
                )

            # ------------------------------------------------------------
            # 3. Filter edges (only between surviving nodes)
            # ------------------------------------------------------------
            allowed_ldns = {n["logicalDatasetName"] for n in filtered_nodes}
            filtered_edges = [
                e
                for e in edges
                if e["source"] in allowed_ldns and e["destination"] in allowed_ldns
            ]

            # ------------------------------------------------------------
            # 4. Build lineage summary using distance
            # ------------------------------------------------------------
            # Group nodes by distance
            nodes_by_distance: dict[int, list[dict[str, str]]] = defaultdict(list)
            for n in filtered_nodes:
                dist = n.get("distance", 0)
                nodes_by_distance[dist].append(n)

            # Build summary chain with parentheses for same-distance nodes
            chain = []
            for dist in sorted(nodes_by_distance):
                dt_list = sorted(
                    {
                        n["dataType"]
                        for n in nodes_by_distance[dist]
                        if n.get("dataType")
                    }
                )
                if len(dt_list) == 1:
                    chain.append(dt_list[0])
                else:
                    chain.append(f"({', '.join(dt_list)})")

            summary = " → ".join(chain) if chain else "No clear chain"

            # ------------------------------------------------------------
            # 5. Format output
            # ------------------------------------------------------------
            parts: list[str] = []

            parts.append("## Lineage Summary")
            parts.append(summary)

            parts.append("\n## Nodes")
            parts.append(format_ami_result(filtered_nodes))

            if filtered_edges:
                parts.append("\n## Edges")
                parts.append(format_ami_result(filtered_edges))

            output = "\n\n".join(parts)

            text = append_next_actions(
                output,
                ["Use `ami_get_dataset_info` on any node LDN for its metadata."],
            )
            payload = AmiDatasetProvResult(
                dataset=dataset,
                found=True,
                summary=summary,
                nodes=rows_to_dicts(filtered_nodes),
                edges=rows_to_dicts(filtered_edges),
            )
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=payload.model_dump(mode="json"),
            )

        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Verify the LDN is complete: project.DSID.physicsShort.prodStep.dataType.tags",
                    "Check that the dataset exists in AMI.",
                    "Use `ami_list_datasets` to search for similar datasets.",
                ],
            )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="List datasets",
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def ami_list_datasets(
        patterns: str,
        project: str,
        fields: str | None = None,
        data_type: str | None = None,
        ami_status: str | None = "VALID",
        limit: int = 100,
        *,
        ctx: Context[Any, Any],
    ) -> Annotated[CallToolResult, AmiListDatasetsResult]:
        """List ATLAS datasets matching a physicsShort pattern via AMI SearchQuery.

        Searches the AMI dataset catalog using the physicsShort field (the
        human-readable process name). Use % as the wildcard character.

        Note: AMI's SearchQuery -entity="dataset" does not support LIKE on
        logicalDatasetName. Filter on physicsShort instead, e.g. "%Zee%" to
        find Zee datasets. The project is required to select the correct catalog.

        The catalog searched depends on both project and data_type: EVNT/HEPMC
        datasets live in the campaign's evgen catalog (e.g. mc20_13TeV EVNT is
        in mc15_001:production -- generated with mc15-era job options), HITS
        in the sim catalog, and everything else (including when data_type is
        omitted) in the campaign's own reco/derivation catalog (e.g.
        mc20_13TeV DAOD_PHYS is in mc20_001:production). Omitting data_type
        assumes a derivation search; pass data_type="EVNT" to reach the evgen
        catalog instead.

        Results are filtered to amiStatus="VALID" by default; pass
        ami_status=None to see all statuses (e.g. TRASHED, OBSOLETE).

        For more control over the query, use ami_execute directly with a
        SearchQuery command (see ami://query-language resource).

        Args:
            patterns: physicsShort pattern with % wildcards, e.g. "%Zee%".
            project: ATLAS project/campaign (e.g. "mc20_13TeV", "mc23_13p6TeV").
                Required to select the correct AMI catalog.
            fields: Comma-separated extra fields to return (e.g. "nFiles,totalEvents").
            data_type: Filter by data type (e.g. "EVNT", "DAOD_PHYS"). Also
                selects the catalog searched -- see above.
            ami_status: Filter by amiStatus (default "VALID"). Pass None to
                search regardless of status.
            limit: Maximum number of results to return (default 100).
        """
        catalog = scope_to_catalog(project, data_type_to_prod_step(data_type))

        conditions: list[str] = [
            f"physicsShort LIKE '{patterns}'",
            f"projectName = '{project}'",
        ]
        if ami_status:
            conditions.append(f"amiStatus = '{ami_status}'")
        if data_type:
            conditions.append(f"dataType = '{data_type}'")

        select_fields = "logicalDatasetName, datasetNumber, physicsShort, amiStatus"
        if fields:
            select_fields += ", " + fields

        mql = f"SELECT {select_fields} WHERE {' AND '.join(conditions)} LIMIT 0,{limit}"
        command = f'SearchQuery -catalog={catalog} -entity=dataset -mql="{mql}"'
        try:
            result = await run_ami_command(ctx, command)
            rows = result.get_rows()
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Use % as wildcard in patterns, e.g. '%Zee%'.",
                    "Verify the project name (e.g. 'mc20_13TeV', 'mc23_13p6TeV').",
                    "Use `ami_search_by_hashtags` to search by physics classification instead.",
                ],
            )

        output = format_ami_result(rows)
        if rows:
            output = append_next_actions(
                output,
                [
                    "Use `ami_get_dataset_info` on a specific LDN for full metadata.",
                    "Use `ami_get_physics_params` on an EVNT LDN for cross-section details.",
                ],
            )
        else:
            status_desc = f"amiStatus='{ami_status}'" if ami_status else "any amiStatus"
            output = append_next_actions(
                output,
                [
                    (
                        f"Searched catalog `{catalog}` with {status_desc}. "
                        "No matches there doesn't mean the dataset doesn't exist."
                    ),
                    (
                        'Pass data_type="EVNT" to search the evgen catalog '
                        "instead of the derivation catalog, or vice versa."
                    ),
                    (
                        "Pass ami_status=None to include non-VALID datasets "
                        "(TRASHED, OBSOLETE, ...)."
                    ),
                ],
            )
        payload = AmiListDatasetsResult(
            patterns=patterns,
            project=project,
            catalog=catalog,
            ami_status=ami_status,
            rows=rows_to_dicts(rows),
            total=len(rows),
        )
        return CallToolResult(
            content=[TextContent(type="text", text=output)],
            structured_content=payload.model_dump(mode="json"),
        )
