"""Tests for ami_validate_sample tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.validate import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from mcp.types import CallToolResult

_LDN = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"

_MC16_HEADER = (
    "dataset_number/I:physics_short/C:crossSection_pb/D:genFiltEff/D:kFactor/D"
)
_MC16_MATCH_ROW = "700320\t\tSh_2211_Zee\t\t1234.5\t\t0.5\t\t1.1"
_MC16_MISMATCH_ROW = "700320\t\tSh_2211_Zee\t\t9999.0\t\t0.5\t\t1.1"


@pytest.fixture
def xsec_dir(tmp_path: Path) -> Path:
    return tmp_path


def _write_db(xsec_dir: Path, row: str) -> None:
    (xsec_dir / "PMGxsecDB_mc16.txt").write_text(
        _MC16_HEADER + "\n" + row + "\n", encoding="utf-8"
    )


@pytest.fixture
def registered_tool() -> Any:
    mcp = MCPServer("test")
    register(mcp)
    return next(
        tool
        for tool in mcp._tool_manager.list_tools()
        if tool.name == "ami_validate_sample"
    )


@pytest.fixture
def registered_tools(
    registered_tool: Any,
) -> dict[str, Callable[..., Awaitable[CallToolResult]]]:
    return {"ami_validate_sample": registered_tool.fn}


def _make_result_mock(rows: list[Any]) -> MagicMock:
    result_mock = MagicMock()
    result_mock.get_rows.return_value = rows
    return result_mock


class TestValidateToolRegistration:
    def test_declares_read_only_annotations(self, registered_tool: Any) -> None:
        assert registered_tool.annotations is not None
        assert registered_tool.annotations.read_only_hint is True
        assert registered_tool.annotations.open_world_hint is True

    def test_publishes_an_output_schema(self, registered_tool: Any) -> None:
        assert registered_tool.output_schema is not None
        assert "datasets" in registered_tool.output_schema["properties"]


class TestAmiValidateSample:
    async def test_no_datasets_provided_is_an_error(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        fn = registered_tools["ami_validate_sample"]
        result = await fn(datasets="   \n  ", ctx=mock_ctx)

        assert result.is_error is True
        assert "no dataset" in tool_text(result).lower()
        assert result.structured_content is None

    async def test_reports_hashtags_without_database(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        hashtag_rows = [
            OrderedDict([("scope", "PMGL1"), ("name", "WeakBoson")]),
            OrderedDict([("scope", "PMGL2"), ("name", "Vjets")]),
        ]
        phys_rows = [OrderedDict([("crossSection", "1.2345"), ("genFiltEff", "0.5")])]

        async def fake_run(_ctx: Any, command: str) -> MagicMock:
            if "DatasetWBListHashtags" in command:
                return _make_result_mock(hashtag_rows)
            return _make_result_mock(phys_rows)

        with patch("ami_mcp.tools.validate.run_ami_command", new=fake_run):
            fn = registered_tools["ami_validate_sample"]
            result = await fn(datasets=_LDN, ctx=mock_ctx)

        output = tool_text(result)
        assert _LDN in output
        assert "WeakBoson" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        ds = result.structured_content["datasets"][0]
        assert ds["dataset"] == _LDN
        assert ds["hashtags"]["PMGL1"] == ["WeakBoson"]
        assert ds["ami_params"]["crossSection"] == "1.2345"
        assert ds["comparisons"] == []
        assert ds["errors"] == []

    async def test_xsec_comparison_ok(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        _write_db(xsec_dir, _MC16_MATCH_ROW)
        phys_rows = [OrderedDict([("crossSection", "1.2345"), ("genFiltEff", "0.5")])]

        async def fake_run(_ctx: Any, command: str) -> MagicMock:
            if "DatasetWBListHashtags" in command:
                return _make_result_mock([])
            return _make_result_mock(phys_rows)

        with (
            patch("ami_mcp.tools.validate.run_ami_command", new=fake_run),
            patch("ami_mcp.tools.validate._get_xsec_path", return_value=xsec_dir),
        ):
            fn = registered_tools["ami_validate_sample"]
            result = await fn(datasets=_LDN, database="mc16", ctx=mock_ctx)

        output = tool_text(result)
        assert "**OK**" in output
        ds = result.structured_content["datasets"][0]
        assert any("OK" in line for line in ds["comparisons"])

    async def test_xsec_comparison_warns_on_mismatch(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        xsec_dir: Path,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        _write_db(xsec_dir, _MC16_MISMATCH_ROW)
        phys_rows = [OrderedDict([("crossSection", "1.2345"), ("genFiltEff", "0.5")])]

        async def fake_run(_ctx: Any, command: str) -> MagicMock:
            if "DatasetWBListHashtags" in command:
                return _make_result_mock([])
            return _make_result_mock(phys_rows)

        with (
            patch("ami_mcp.tools.validate.run_ami_command", new=fake_run),
            patch("ami_mcp.tools.validate._get_xsec_path", return_value=xsec_dir),
        ):
            fn = registered_tools["ami_validate_sample"]
            result = await fn(datasets=_LDN, database="mc16", ctx=mock_ctx)

        output = tool_text(result)
        assert "**WARNING**" in output
        ds = result.structured_content["datasets"][0]
        assert any("WARNING" in line for line in ds["comparisons"])

    async def test_hashtag_lookup_error_is_recorded_not_raised(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        async def fake_run(_ctx: Any, command: str) -> MagicMock:
            if "DatasetWBListHashtags" in command:
                msg = "AMI down"
                raise RuntimeError(msg)
            return _make_result_mock([])

        with patch("ami_mcp.tools.validate.run_ami_command", new=fake_run):
            fn = registered_tools["ami_validate_sample"]
            result = await fn(datasets=_LDN, ctx=mock_ctx)

        output = tool_text(result)
        assert "Hashtag lookup error" in output
        assert result.is_error is not True
        ds = result.structured_content["datasets"][0]
        assert any("Hashtag lookup error" in e for e in ds["errors"])

    async def test_multiple_datasets_each_get_a_section(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.validate.run_ami_command",
            new=AsyncMock(return_value=_make_result_mock([])),
        ):
            fn = registered_tools["ami_validate_sample"]
            result = await fn(datasets=f"{_LDN}\nother.dataset", ctx=mock_ctx)

        output = tool_text(result)
        assert _LDN in output
        assert "other.dataset" in output
        assert len(result.structured_content["datasets"]) == 2
