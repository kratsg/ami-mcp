"""Tests for MCP resources."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ami_mcp.resources import register


class TestResources:
    def test_resources_registered(self) -> None:
        mcp = FastMCP("test")
        register(mcp)
        resources = mcp._resource_manager.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ami://query-language" in uris
        assert "ami://atlas-nomenclature" in uris
        assert "ami://pmg-xsec-database" in uris

    def test_query_language_contains_searchquery(self) -> None:
        mcp = FastMCP("test")
        register(mcp)
        resources = {str(r.uri): r for r in mcp._resource_manager.list_resources()}
        fn = resources["ami://query-language"].fn  # type: ignore[attr-defined]
        content = fn()
        assert "SearchQuery" in content

    def test_nomenclature_contains_pmgl(self) -> None:
        mcp = FastMCP("test")
        register(mcp)
        resources = {str(r.uri): r for r in mcp._resource_manager.list_resources()}
        fn = resources["ami://atlas-nomenclature"].fn  # type: ignore[attr-defined]
        content = fn()
        assert "PMGL1" in content
        assert "PMGL3" in content

    def test_xsec_db_contains_column_info(self) -> None:
        mcp = FastMCP("test")
        register(mcp)
        resources = {str(r.uri): r for r in mcp._resource_manager.list_resources()}
        fn = resources["ami://pmg-xsec-database"].fn  # type: ignore[attr-defined]
        content = fn()
        assert "crossSection_pb" in content
        assert "genFiltEff" in content
