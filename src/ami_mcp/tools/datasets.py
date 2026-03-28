"""AMI dataset info tools."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mcp.server.fastmcp import Context, FastMCP  # noqa: TC002

from ami_mcp.tools._helpers import (
    append_next_actions,
    format_ami_result,
    format_error,
    run_ami_sync,
    scope_to_catalog,
)

_DATASET_INFO_FIELDS = [
    "logicalDatasetName",
    "datasetNumber",
    "physicsShort",
    "nFiles",
    "nEvents",
    "totalSize",
    "crossSection",
    "genFiltEff",
    "kFactor",
    "amiStatus",
    "prodsysStatus",
    "dataType",
    "prodStep",
    "projectName",
    "version",
]


def register(mcp: FastMCP) -> None:
    """Register dataset info tools."""

    @mcp.tool()
    async def ami_get_dataset_info(
        dataset: str,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Get metadata for an ATLAS dataset (LDN) from AMI.

        Returns key fields: nFiles, nEvents, totalSize, crossSection, genFiltEff,
        amiStatus, and related metadata registered in AMI for this dataset.
        Use ami_execute with AMIGetDatasetInfo for all raw fields.

        Args:
            dataset: Full Logical Dataset Name (LDN), e.g.
                "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.deriv.DAOD_PHYS.e8351_s3681_r13144_r13146_p5855"
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'AMIGetDatasetInfo -logicalDatasetName="{dataset}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
            if not rows:
                return "No results."
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

            return append_next_actions(output, hints)
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Verify the LDN is complete: project.DSID.physicsShort.prodStep.dataType.tags",
                    "Use `ami_list_datasets` to search by physicsShort pattern.",
                ],
            )

    @mcp.tool()
    async def ami_get_dataset_prov(
        dataset: str,
        data_types: str | None = "EVNT,HITS,RDO,ESD,AOD,HEPMC,DAOD_",
        *,
        ctx: Context[Any, Any],
    ) -> str:
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
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'AMIGetDatasetProv -logicalDatasetName="{dataset}"'

        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            nodes = result.get_rows("node")
            edges = result.get_rows("edge")

            if not nodes:
                return "No provenance found."

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
                return "No nodes remain after filtering."

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

            return append_next_actions(
                output,
                ["Use `ami_get_dataset_info` on any node LDN for its metadata."],
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

    @mcp.tool()
    async def ami_list_datasets(
        patterns: str,
        project: str,
        fields: str | None = None,
        data_type: str | None = None,
        limit: int = 100,
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """List ATLAS datasets matching a physicsShort pattern via AMI SearchQuery.

        Searches the AMI dataset catalog using the physicsShort field (the
        human-readable process name). Use % as the wildcard character.

        Note: AMI's SearchQuery -entity="dataset" does not support LIKE on
        logicalDatasetName. Filter on physicsShort instead, e.g. "%Zee%" to
        find Zee datasets. The project is required to select the correct catalog.

        For more control over the query, use ami_execute directly with a
        SearchQuery command (see ami://query-language resource).

        Args:
            patterns: physicsShort pattern with % wildcards, e.g. "%Zee%".
            project: ATLAS project/campaign (e.g. "mc20_13TeV", "mc23_13p6TeV").
                Required to select the correct AMI catalog.
            fields: Comma-separated extra fields to return (e.g. "nFiles,nEvents").
            data_type: Filter by data type (e.g. "EVNT", "DAOD_PHYS").
            limit: Maximum number of results to return (default 100).
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        catalog = scope_to_catalog(project)

        conditions: list[str] = [
            f"physicsShort LIKE '{patterns}'",
            f"projectName = '{project}'",
            "amiStatus = 'VALID'",
        ]
        if data_type:
            conditions.append(f"dataType = '{data_type}'")

        select_fields = "logicalDatasetName, datasetNumber, physicsShort, amiStatus"
        if fields:
            select_fields += ", " + fields

        mql = f"SELECT {select_fields} WHERE {' AND '.join(conditions)} LIMIT 0,{limit}"
        command = f'SearchQuery -catalog={catalog} -entity=dataset -mql="{mql}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
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
        return output
