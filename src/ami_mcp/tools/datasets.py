"""AMI dataset info tools."""

from __future__ import annotations

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
            return append_next_actions(
                output,
                [
                    "Use `ami_get_dataset_prov` to trace the processing chain (EVNT→HITS→AOD→DAOD).",
                    "Use `ami_get_physics_params` on the EVNT LDN for cross-section details.",
                    "Use `ami_get_dataset_hashtags` on an EVNT LDN for PMG classification.",
                ],
            )
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
        *,
        ctx: Context[Any, Any],
    ) -> str:
        """Get the provenance (parent/child chain) for an ATLAS dataset.

        Use this to trace a DAOD back to its EVNT, or to find derived datasets
        from an EVNT. Returns node and edge information showing the dataset's
        processing lineage (e.g. EVNT → HITS → RDO → AOD → DAOD).

        Args:
            dataset: Full Logical Dataset Name (LDN).
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        command = f'AMIGetDatasetProv -logicalDatasetName="{dataset}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            nodes = result.get_rows("node")
            edges = result.get_rows("edge")
            parts: list[str] = []
            if nodes:
                parts.append("## Nodes")
                parts.append(format_ami_result(nodes))
            if edges:
                parts.append("## Edges")
                parts.append(format_ami_result(edges))
            if not parts:
                return "No provenance found."
            output = "\n\n".join(parts)
            return append_next_actions(
                output,
                ["Use `ami_get_dataset_info` on any node LDN for its metadata."],
            )
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

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

        mql = f"SELECT {select_fields} WHERE {' AND '.join(conditions)} LIMIT {limit}"
        command = f'SearchQuery -catalog="{catalog}" -entity="dataset" -mql="{mql}"'
        try:
            result = await run_ami_sync(client.execute, command, format="dom_object")
            rows = result.get_rows()
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
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
