"""MCP resources exposing ATLAS AMI documentation to the LLM."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # noqa: TC002

from ami_mcp.nomenclature import (
    AMI_QUERY_LANGUAGE,
    ATLAS_NOMENCLATURE,
    PMG_XSEC_DATABASE,
)


def register(mcp: FastMCP) -> None:
    """Register documentation resources with the MCP server."""

    @mcp.resource(
        "ami://query-language",
        name="AMI Query Language Reference",
        description=(
            "Complete reference for AMI command syntax and MQL. "
            "Read this to learn how to construct query strings for ami_execute: "
            "SearchQuery syntax, catalogs, entities, field names, wildcards, "
            "DatasetWB commands, and worked examples."
        ),
        mime_type="text/plain",
    )
    def get_query_language() -> str:
        return AMI_QUERY_LANGUAGE

    @mcp.resource(
        "ami://atlas-nomenclature",
        name="ATLAS Dataset Nomenclature",
        description=(
            "ATLAS dataset naming conventions: LDN format, MC/data campaign scopes, "
            "PMG hashtag hierarchy (PMGL1-4), AMI tag letters, prodStep/dataType values, "
            "and standard physics metadata fields."
        ),
        mime_type="text/plain",
    )
    def get_atlas_nomenclature() -> str:
        return ATLAS_NOMENCLATURE

    @mcp.resource(
        "ami://pmg-xsec-database",
        name="PMG Cross-Section Database Reference",
        description=(
            "Reference for PMG cross-section database files (PMGxsecDB_*.txt): "
            "file location on CVMFS, naming convention, column schema, units "
            "(pb vs nb), and how DSID+etag uniquely identifies a sample entry."
        ),
        mime_type="text/plain",
    )
    def get_pmg_xsec_database() -> str:
        return PMG_XSEC_DATABASE
