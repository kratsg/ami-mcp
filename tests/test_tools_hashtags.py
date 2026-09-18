"""Tests for hashtag tools."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.hashtags import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.types import CallToolResult


@pytest.fixture
def registered_tool_objs() -> dict[str, Any]:
    mcp = MCPServer("test")
    register(mcp)
    return {tool.name: tool for tool in mcp._tool_manager.list_tools()}


@pytest.fixture
def registered_tools(
    registered_tool_objs: dict[str, Any],
) -> dict[str, Callable[..., Awaitable[CallToolResult]]]:
    return {name: tool.fn for name, tool in registered_tool_objs.items()}


class TestHashtagsToolRegistration:
    @pytest.mark.parametrize(
        "name", ["ami_search_by_hashtags", "ami_get_dataset_hashtags"]
    )
    def test_declares_read_only_annotations(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        tool = registered_tool_objs[name]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is True

    @pytest.mark.parametrize(
        "name", ["ami_search_by_hashtags", "ami_get_dataset_hashtags"]
    )
    def test_publishes_an_output_schema(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        assert registered_tool_objs[name].output_schema is not None


class TestAmiSearchByHashtags:
    async def test_builds_correct_command(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("ldn", "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351")])
        ]

        executed_commands: list[str] = []

        async def capture_run_ami_command(_func, *args, **_kwargs):
            if args:
                executed_commands.append(str(args[0]))
            return result_mock

        with patch(
            "ami_mcp.tools.hashtags.run_ami_command", new=capture_run_ami_command
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            await fn(
                scope="mc20_13TeV",
                l1="WeakBoson",
                l2="Vjets",
                l3="Baseline",
                ctx=mock_ctx,
            )

        assert len(executed_commands) == 1
        cmd = executed_commands[0]
        assert "DatasetWBListDatasetsForHashtag" in cmd
        assert '-scope="PMGL1,PMGL2,PMGL3"' in cmd
        assert '-name="WeakBoson,Vjets,Baseline"' in cmd
        assert '-operator="AND"' in cmd
        # campaign scope is applied client-side, not in the AMI command
        assert "mc20_13TeV" not in cmd

    async def test_returns_datasets(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("ldn", "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351")])
        ]
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(scope="mc20_13TeV", l1="WeakBoson", ctx=mock_ctx)

        output = tool_text(result)
        assert (
            "| 700320 | Sh_2211_Zee | `mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351` |"
            in output
        )
        assert "**Scope:** mc20_13TeV" in output
        assert "## Matching Datasets" in output
        assert result.structured_content is not None
        assert result.structured_content["datasets"] == [
            {
                "dsid": "700320",
                "physics_short": "Sh_2211_Zee",
                "ldn": "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351",
            }
        ]

    async def test_returns_only_ldns(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        """Result should be LDN table with dsid/physicsShort/ldn columns."""
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict(
                [
                    ("id", "12345"),
                    ("catalog", "mc15_001:production"),
                    ("ldn", "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"),
                ]
            )
        ]
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(scope="mc20_13TeV", l1="WeakBoson", ctx=mock_ctx)

        output = tool_text(result)
        assert "| DSID | physicsShort | LDN |" in output
        assert (
            "| 700320 | Sh_2211_Zee | `mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351` |"
            in output
        )
        # Keep these to ensure extraneous columns/fields are not included
        assert "catalog" not in output
        assert "12345" not in output
        assert "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351" in output

    async def test_no_datasets_match_scope(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = []
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(scope="mc20_13TeV", l1="WeakBoson", ctx=mock_ctx)

        assert "No results." in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["datasets"] == []

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("no proxy")),
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(scope="mc20_13TeV", l1="WeakBoson", ctx=mock_ctx)

        output = tool_text(result)
        assert "**Error**:" in output  # still matches
        assert "Check that the hashtag levels exist" in output  # optional hint check
        assert result.is_error is True


class TestAmiGetDatasetHashtags:
    async def test_returns_hashtag_levels(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        rows = [
            OrderedDict([("SCOPE", "PMGL1"), ("NAME", "WeakBoson")]),
            OrderedDict([("SCOPE", "PMGL2"), ("NAME", "Vjets")]),
            OrderedDict([("SCOPE", "PMGL3"), ("NAME", "Baseline")]),
        ]
        result_mock = MagicMock()
        result_mock.get_rows.return_value = rows
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_hashtags"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        output = tool_text(result)
        assert "WeakBoson" in output
        assert "Baseline" in output
        assert result.structured_content is not None
        assert result.structured_content["found"] is True
        assert result.structured_content["hashtags"]["PMGL1"] == ["WeakBoson"]

    async def test_non_evnt_shows_warning(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        rows = [OrderedDict([("SCOPE", "PMGL1"), ("NAME", "WeakBoson")])]
        result_mock = MagicMock()
        result_mock.get_rows.return_value = rows
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_hashtags"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.deriv.DAOD_PHYS.e8351_s3681_p5855",
                ctx=mock_ctx,
            )

        output = tool_text(result)
        assert "Note:" in output
        assert "EVNT" in output

    async def test_no_hashtags_found(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = []
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_hashtags"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        assert "No hashtags found" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["found"] is False

    async def test_returns_error_with_hints(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.hashtags.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("connection error")),
        ):
            fn = registered_tools["ami_get_dataset_hashtags"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        output = tool_text(result)
        assert "**Error**:" in output
        assert "EVNT" in output
        assert result.is_error is True
