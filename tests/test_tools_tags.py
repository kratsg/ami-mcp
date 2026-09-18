"""Tests for AMI tag info tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.tags import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.types import CallToolResult


@pytest.fixture
def registered_tool() -> Any:
    mcp = MCPServer("test")
    register(mcp)
    return next(
        tool
        for tool in mcp._tool_manager.list_tools()
        if tool.name == "ami_get_ami_tag"
    )


@pytest.fixture
def registered_tools(
    registered_tool: Any,
) -> dict[str, Callable[..., Awaitable[CallToolResult]]]:
    return {"ami_get_ami_tag": registered_tool.fn}


class TestTagsToolRegistration:
    def test_declares_read_only_annotations(self, registered_tool: Any) -> None:
        assert registered_tool.annotations is not None
        assert registered_tool.annotations.read_only_hint is True
        assert registered_tool.annotations.open_world_hint is True

    def test_publishes_an_output_schema(self, registered_tool: Any) -> None:
        assert registered_tool.output_schema is not None
        assert "rows" in registered_tool.output_schema["properties"]


class TestAmiGetAmiTag:
    async def test_returns_tag_info(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        rows = [
            OrderedDict(
                [
                    ("tagType", "e"),
                    ("tagNumber", "8351"),
                    ("description", "Sherpa 2.2.11 Zee"),
                ]
            )
        ]
        result_mock = MagicMock()
        result_mock.get_rows.return_value = rows
        with patch(
            "ami_mcp.tools.tags.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_ami_tag"]
            result = await fn(tag="e8351", ctx=mock_ctx)

        output = tool_text(result)
        assert "8351" in output
        assert "Sherpa" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        assert result.structured_content["first_tag"] == "e8351"
        assert result.structured_content["remaining_tags"] == []
        assert (
            result.structured_content["rows"][0]["description"] == "Sherpa 2.2.11 Zee"
        )

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.tags.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("tag not found")),
        ):
            fn = registered_tools["ami_get_ami_tag"]
            result = await fn(tag="e9999", ctx=mock_ctx)

        output = tool_text(result)
        assert "**Error**:" in output
        assert "Tag format" in output
        assert result.is_error is True

    async def test_tag_chain_uses_first_tag(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        """When a full tag chain is passed, look up only the first tag."""
        rows = [
            OrderedDict(
                [("tagType", "e"), ("tagNumber", "8351"), ("description", "evgen")]
            )
        ]
        result_mock = MagicMock()
        result_mock.get_rows.return_value = rows

        executed_commands: list[str] = []

        async def capture(_func, *args, **_kwargs):
            executed_commands.append(str(args[0]))
            return result_mock

        with patch("ami_mcp.tools.tags.run_ami_command", new=capture):
            fn = registered_tools["ami_get_ami_tag"]
            result = await fn(tag="e8351_s3681_r13144", ctx=mock_ctx)

        assert len(executed_commands) == 1
        assert '-amiTag="e8351"' in executed_commands[0]
        # Remaining tags hinted in next steps
        output = tool_text(result)
        assert "s3681" in output
        assert "r13144" in output
        assert result.structured_content["remaining_tags"] == ["s3681", "r13144"]
