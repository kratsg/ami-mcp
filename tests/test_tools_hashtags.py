"""Tests for hashtag tools."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.hashtags import register


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@pytest.fixture
def registered_tools() -> dict[str, Callable[..., Awaitable[str]]]:
    mcp = FastMCP("test")
    register(mcp)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


class TestAmiSearchByHashtags:
    async def test_builds_correct_command(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        mock_ami_client: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("logicalDatasetName", "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351")])
        ]

        executed_commands: list[str] = []

        async def capture_run_ami_sync(func, *args, **kwargs):  # type: ignore[no-untyped-def]
            if args:
                executed_commands.append(str(args[0]))
            return result_mock

        with patch("ami_mcp.tools.hashtags.run_ami_sync", new=capture_run_ami_sync):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(
                scope="mc20_13TeV", l1="WeakBoson", l2="Vjets", l3="Baseline", ctx=mock_ctx
            )

        assert len(executed_commands) == 1
        cmd = executed_commands[0]
        assert "DatasetWBListDatasetsForHashtag" in cmd
        assert "mc20_13TeV" in cmd
        assert "WeakBoson" in cmd
        assert "Vjets" in cmd
        assert "Baseline" in cmd

    async def test_returns_datasets(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("logicalDatasetName", "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351")])
        ]
        with patch(
            "ami_mcp.tools.hashtags.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(scope="mc20_13TeV", l1="WeakBoson", ctx=mock_ctx)

        assert "700320" in result

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        with patch(
            "ami_mcp.tools.hashtags.run_ami_sync",
            new=AsyncMock(side_effect=RuntimeError("no proxy")),
        ):
            fn = registered_tools["ami_search_by_hashtags"]
            result = await fn(scope="mc20_13TeV", l1="WeakBoson", ctx=mock_ctx)

        assert result.startswith("Error:")


class TestAmiGetDatasetHashtags:
    async def test_returns_hashtag_levels(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        rows = [
            OrderedDict([("SCOPE", "PMGL1"), ("NAME", "WeakBoson")]),
            OrderedDict([("SCOPE", "PMGL2"), ("NAME", "Vjets")]),
            OrderedDict([("SCOPE", "PMGL3"), ("NAME", "Baseline")]),
        ]
        result_mock = MagicMock()
        result_mock.get_rows.return_value = rows
        with patch(
            "ami_mcp.tools.hashtags.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_hashtags"]
            result = await fn(dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx)

        assert "WeakBoson" in result
        assert "Baseline" in result
