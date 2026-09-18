"""Tests for ami_execute tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.execute import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.types import CallToolResult


@pytest.fixture
def registered_tool() -> Any:
    mcp = MCPServer("test")
    register(mcp)
    return next(
        tool for tool in mcp._tool_manager.list_tools() if tool.name == "ami_execute"
    )


@pytest.fixture
def registered_tools(
    registered_tool: Any,
) -> dict[str, Callable[..., Awaitable[CallToolResult]]]:
    return {"ami_execute": registered_tool.fn}


class TestAmiExecuteRegistration:
    def test_declares_read_only_annotations(self, registered_tool: Any) -> None:
        assert registered_tool.annotations is not None
        assert registered_tool.annotations.read_only_hint is True
        assert registered_tool.annotations.open_world_hint is True

    def test_publishes_an_output_schema(self, registered_tool: Any) -> None:
        assert registered_tool.output_schema is not None
        assert "rows" in registered_tool.output_schema["properties"]


class TestAmiExecute:
    async def test_returns_formatted_results(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        mock_ami_client: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])
        ]
        mock_ami_client.execute.return_value = result_mock

        with patch(
            "ami_mcp.tools.execute.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_execute"]
            result = await fn(command='SearchQuery -catalog="mc23"', ctx=mock_ctx)

        output = tool_text(result)
        assert "WeakBoson" in output
        assert "PMGL1" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        assert result.structured_content["command"] == 'SearchQuery -catalog="mc23"'
        assert result.structured_content["total"] == 1
        assert result.structured_content["rows"][0] == {
            "NAME": "WeakBoson",
            "SCOPE": "PMGL1",
        }

    async def test_returns_no_results_on_empty(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = []

        with patch(
            "ami_mcp.tools.execute.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_execute"]
            result = await fn(command="SomeQuery", ctx=mock_ctx)

        assert "No results" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["rows"] == []
        assert result.structured_content["total"] == 0

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.execute.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("auth failed")),
        ):
            fn = registered_tools["ami_execute"]
            result = await fn(command="BadCommand", ctx=mock_ctx)

        assert "Error" in tool_text(result)
        assert result.is_error is True
        assert result.structured_content is None
