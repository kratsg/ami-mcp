"""Tests for PMG cross-section database tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.xsecdb import _parse_db_file, register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from mcp.types import CallToolResult

# A minimal PMGxsecDB file for testing
_MC16_HEADER = "dataset_number/I:physics_short/C:crossSection_pb/D:genFiltEff/D:kFactor/D:relUncertUP/D:relUncertDOWN/D:generator_name/C:etag/C"
_MC16_ROWS = [
    "700320\t\tSh_2211_Zee\t\t1234.5\t\t0.5\t\t1.1\t\t0.05\t\t0.05\t\tSherpa\t\te8351",
    "700320\t\tSh_2211_Zee\t\t1300.0\t\t0.6\t\t1.0\t\t0.03\t\t0.03\t\tSherpa\t\te8999",
    "700321\t\tSh_2211_Zmm\t\t1234.5\t\t1.0\t\t1.0\t\t0.05\t\t0.05\t\tSherpa\t\te8351",
]

# An older file that uses nb instead of pb
_MC15_HEADER = "dataset_number/I:physics_short/C:crossSection/D:genFiltEff/D:kFactor/D:relUncertUP/D:relUncertDOWN/D:generator_name/C:etag/C"
_MC15_ROWS = [
    "361020\t\tSh_221_Zee\t\t1.2345\t\t1.0\t\t1.0\t\t0.05\t\t0.05\t\tSherpa\t\te5421",
]


@pytest.fixture
def xsec_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with fixture DB files."""
    mc16_file = tmp_path / "PMGxsecDB_mc16.txt"
    mc16_file.write_text(
        _MC16_HEADER + "\n" + "\n".join(_MC16_ROWS) + "\n",
        encoding="utf-8",
    )
    mc15_file = tmp_path / "PMGxsecDB_mc15.txt"
    mc15_file.write_text(
        _MC15_HEADER + "\n" + "\n".join(_MC15_ROWS) + "\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def registered_tool_objs(xsec_dir: Path) -> dict[str, Any]:  # noqa: ARG001
    mcp = MCPServer("test")
    register(mcp)
    return {tool.name: tool for tool in mcp._tool_manager.list_tools()}


@pytest.fixture
def registered_tools(
    registered_tool_objs: dict[str, Any],
) -> dict[str, Callable[..., Awaitable[CallToolResult]]]:
    return {name: tool.fn for name, tool in registered_tool_objs.items()}


class TestXsecdbToolRegistration:
    @pytest.mark.parametrize("name", ["ami_list_xsec_databases", "ami_lookup_xsec"])
    def test_declares_read_only_annotations(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        tool = registered_tool_objs[name]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is True

    @pytest.mark.parametrize("name", ["ami_list_xsec_databases", "ami_lookup_xsec"])
    def test_publishes_an_output_schema(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        assert registered_tool_objs[name].output_schema is not None


class TestParseDbFile:
    def test_finds_dsid(self, xsec_dir: Path) -> None:
        rows = _parse_db_file(xsec_dir / "PMGxsecDB_mc16.txt", 700320, None)
        assert len(rows) == 2
        assert all(r["dataset_number"] == "700320" for r in rows)

    def test_filters_by_etag(self, xsec_dir: Path) -> None:
        rows = _parse_db_file(xsec_dir / "PMGxsecDB_mc16.txt", 700320, "e8351")
        assert len(rows) == 1
        assert rows[0]["etag"] == "e8351"
        assert rows[0]["crossSection_pb"] == "1234.5"

    def test_no_match_returns_empty(self, xsec_dir: Path) -> None:
        rows = _parse_db_file(xsec_dir / "PMGxsecDB_mc16.txt", 999999, None)
        assert rows == []

    def test_different_dsid(self, xsec_dir: Path) -> None:
        rows = _parse_db_file(xsec_dir / "PMGxsecDB_mc16.txt", 700321, None)
        assert len(rows) == 1
        assert rows[0]["physics_short"] == "Sh_2211_Zmm"


class TestAmiListXsecDatabases:
    async def test_lists_available_files(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_list_xsec_databases"]
            result = await fn(ctx=mock_ctx)

        output = tool_text(result)
        assert "PMGxsecDB_mc16.txt" in output
        assert "PMGxsecDB_mc15.txt" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        files = {d["file"] for d in result.structured_content["databases"]}
        assert files == {"PMGxsecDB_mc16.txt", "PMGxsecDB_mc15.txt"}

    async def test_no_files_found(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tmp_path: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=empty_dir):
            fn = registered_tools["ami_list_xsec_databases"]
            result = await fn(ctx=mock_ctx)

        assert "No PMGxsecDB" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["databases"] == []

    async def test_error_when_path_missing(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tmp_path: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        nonexistent = tmp_path / "nonexistent"
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=nonexistent):
            fn = registered_tools["ami_list_xsec_databases"]
            result = await fn(ctx=mock_ctx)

        assert "Error" in tool_text(result)
        assert result.is_error is True
        assert result.structured_content is None


class TestAmiLookupXsec:
    async def test_lookup_by_dsid_and_etag(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, database="mc16", etag="e8351", ctx=mock_ctx)

        output = tool_text(result)
        assert "1234.5" in output
        assert "pb" in output
        assert "0.5" in output  # genFiltEff
        assert result.structured_content is not None
        assert len(result.structured_content["entries"]) == 1
        assert result.structured_content["entries"][0]["source"] == "PMGxsecDB_mc16.txt"

    async def test_lookup_returns_all_rows_without_etag(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, database="mc16", ctx=mock_ctx)

        output = tool_text(result)
        assert "e8351" in output
        assert "e8999" in output
        assert len(result.structured_content["entries"]) == 2

    async def test_lookup_with_full_filename(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(
                dsid=700320, database="PMGxsecDB_mc16.txt", etag="e8351", ctx=mock_ctx
            )

        assert "1234.5" in tool_text(result)

    async def test_lookup_nb_file_converts_to_pb(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=361020, database="mc15", ctx=mock_ctx)

        output = tool_text(result)
        # 1.2345 nb * 1000 = 1234.5 pb
        assert "1234.5" in output
        assert "nb" in output

    async def test_lookup_missing_dsid_returns_message(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=999999, database="mc16", ctx=mock_ctx)

        assert "No matching" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["entries"] == []

    async def test_lookup_missing_database_file(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, database="mc99", ctx=mock_ctx)

        output = tool_text(result)
        assert "Error" in output
        assert "not found" in output
        assert result.is_error is True

    async def test_lookup_no_database_specified_and_none_found(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tmp_path: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=empty_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, ctx=mock_ctx)

        assert "No PMGxsecDB" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["entries"] == []
