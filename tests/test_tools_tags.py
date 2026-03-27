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

        assert result.startswith("Error:")
