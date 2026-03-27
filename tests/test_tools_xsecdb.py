"""Tests for PMG cross-section database tools."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.xsecdb import _parse_db_file, register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

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
def registered_tools(xsec_dir: Path) -> dict[str, Callable[..., Awaitable[str]]]:  # noqa: ARG001
    mcp = FastMCP("test")
    register(mcp)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


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
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_list_xsec_databases"]
            result = await fn(ctx=mock_ctx)

        assert "PMGxsecDB_mc16.txt" in result
        assert "PMGxsecDB_mc15.txt" in result

    async def test_error_when_path_missing(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        tmp_path: Path,
    ) -> None:
        nonexistent = tmp_path / "nonexistent"
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=nonexistent):
            fn = registered_tools["ami_list_xsec_databases"]
            result = await fn(ctx=mock_ctx)

        assert "Error" in result


class TestAmiLookupXsec:
    async def test_lookup_by_dsid_and_etag(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, database="mc16", etag="e8351", ctx=mock_ctx)

        assert "1234.5" in result
        assert "pb" in result
        assert "0.5" in result  # genFiltEff

    async def test_lookup_returns_all_rows_without_etag(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, database="mc16", ctx=mock_ctx)

        assert "e8351" in result
        assert "e8999" in result

    async def test_lookup_with_full_filename(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(
                dsid=700320, database="PMGxsecDB_mc16.txt", etag="e8351", ctx=mock_ctx
            )

        assert "1234.5" in result

    async def test_lookup_nb_file_converts_to_pb(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=361020, database="mc15", ctx=mock_ctx)

        # 1.2345 nb * 1000 = 1234.5 pb
        assert "1234.5" in result
        assert "nb" in result

    async def test_lookup_missing_dsid_returns_message(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=999999, database="mc16", ctx=mock_ctx)

        assert "No matching" in result

    async def test_lookup_missing_database_file(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
    ) -> None:
        with patch("ami_mcp.tools.xsecdb._get_xsec_path", return_value=xsec_dir):
            fn = registered_tools["ami_lookup_xsec"]
            result = await fn(dsid=700320, database="mc99", ctx=mock_ctx)

        assert "Error" in result
        assert "not found" in result
