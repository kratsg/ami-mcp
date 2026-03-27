"""Tests for physics params tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.physics import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@pytest.fixture
def registered_tools() -> dict[str, Callable[..., Awaitable[str]]]:
    mcp = FastMCP("test")
    register(mcp)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


class TestAmiGetPhysicsParams:
    async def test_converts_crosssection_nb_to_pb(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict(
                [
                    ("crossSection", "1.234"),
                    ("genFiltEff", "0.5"),
                    ("kFactor", "1.0"),
                ]
            )
        ]
        with patch(
            "ami_mcp.tools.physics.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        # 1.234 nb * 1000 = 1234 pb
        assert "1234" in result
        assert "pb" in result

    async def test_returns_other_fields(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict(
                [
                    ("crossSection", "0.5"),
                    ("genFiltEff", "0.25"),
                    ("kFactor", "1.1"),
                    ("contactPerson", "jsmith"),
                ]
            )
        ]
        with patch(
            "ami_mcp.tools.physics.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(dataset="some.dataset.EVNT.e1234", ctx=mock_ctx)

        assert "genFiltEff" in result
        assert "0.25" in result
        assert "jsmith" in result

    async def test_returns_no_params_message_on_empty(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = []
        with patch(
            "ami_mcp.tools.physics.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(
                dataset="mc20_13TeV.999999.None.evgen.EVNT.e0000", ctx=mock_ctx
            )

        assert "No physics parameters" in result

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        with patch(
            "ami_mcp.tools.physics.run_ami_sync",
            new=AsyncMock(side_effect=RuntimeError("timeout")),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(dataset="bad.dataset", ctx=mock_ctx)

        assert result.startswith("Error:")
