"""Tests for AMI tag info tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.tags import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@pytest.fixture
def registered_tools() -> dict[str, Callable[..., Awaitable[str]]]:
    mcp = FastMCP("test")
    register(mcp)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


class TestAmiGetAmiTag:
    async def test_returns_tag_info(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
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
            "ami_mcp.tools.tags.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_ami_tag"]
            result = await fn(tag="e8351", ctx=mock_ctx)

        assert "8351" in result
        assert "Sherpa" in result

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        with patch(
            "ami_mcp.tools.tags.run_ami_sync",
            new=AsyncMock(side_effect=RuntimeError("tag not found")),
        ):
            fn = registered_tools["ami_get_ami_tag"]
            result = await fn(tag="e9999", ctx=mock_ctx)

        assert "**Error**:" in result
        assert "Tag format" in result

    async def test_tag_chain_uses_first_tag(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
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

        with patch("ami_mcp.tools.tags.run_ami_sync", new=capture):
            fn = registered_tools["ami_get_ami_tag"]
            result = await fn(tag="e8351_s3681_r13144", ctx=mock_ctx)

        assert len(executed_commands) == 1
        assert '-amiTag="e8351"' in executed_commands[0]
        # Remaining tags hinted in next steps
        assert "s3681" in result
        assert "r13144" in result
