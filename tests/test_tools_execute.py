"""Tests for ami_execute tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.execute import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@pytest.fixture
def registered_tools() -> dict[str, Callable[..., Awaitable[str]]]:
    mcp = FastMCP("test")
    register(mcp)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


class TestAmiExecute:
    async def test_returns_formatted_results(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
        mock_ami_client: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])
        ]
        mock_ami_client.execute.return_value = result_mock

        with patch(
            "ami_mcp.tools.execute.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_execute"]
            result = await fn(command='SearchQuery -catalog="mc23"', ctx=mock_ctx)

        assert "WeakBoson" in result
        assert "PMGL1" in result

    async def test_returns_no_results_on_empty(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = []

        with patch(
            "ami_mcp.tools.execute.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_execute"]
            result = await fn(command="SomeQuery", ctx=mock_ctx)

        assert "No results" in result

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        with patch(
            "ami_mcp.tools.execute.run_ami_sync",
            new=AsyncMock(side_effect=RuntimeError("auth failed")),
        ):
            fn = registered_tools["ami_execute"]
            result = await fn(command="BadCommand", ctx=mock_ctx)

        assert "Error" in result
