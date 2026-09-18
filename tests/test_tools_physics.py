"""Tests for physics params tool."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.physics import register

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
        if tool.name == "ami_get_physics_params"
    )


@pytest.fixture
def registered_tools(
    registered_tool: Any,
) -> dict[str, Callable[..., Awaitable[CallToolResult]]]:
    return {"ami_get_physics_params": registered_tool.fn}


class TestPhysicsToolRegistration:
    def test_declares_read_only_annotations(self, registered_tool: Any) -> None:
        assert registered_tool.annotations is not None
        assert registered_tool.annotations.read_only_hint is True
        assert registered_tool.annotations.open_world_hint is True

    def test_publishes_an_output_schema(self, registered_tool: Any) -> None:
        assert registered_tool.output_schema is not None
        assert "params" in registered_tool.output_schema["properties"]


class TestAmiGetPhysicsParams:
    async def test_converts_crosssection_nb_to_pb(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict(
                [
                    ("paramName", "crossSection"),
                    ("paramValue", "1.234"),
                    ("units", "nb"),
                ]
            ),
            OrderedDict(
                [
                    ("paramName", "genFiltEff"),
                    ("paramValue", "0.5"),
                    ("units", "NULL"),
                ]
            ),
        ]
        with patch(
            "ami_mcp.tools.physics.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        output = tool_text(result)
        # 1.234 nb * 1000 = 1234 pb
        assert "1234" in output
        assert "pb" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        assert result.structured_content["found"] is True
        assert result.structured_content["params"]["crossSection"] == {
            "value": "1.234",
            "units": "nb",
        }
        assert result.structured_content["params"]["genFiltEff"] == {
            "value": "0.5",
            "units": "",
        }

    async def test_returns_other_fields(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict(
                [
                    ("paramName", "crossSection"),
                    ("paramValue", "0.5"),
                    ("units", "nb"),
                ]
            ),
            OrderedDict(
                [
                    ("paramName", "genFiltEff"),
                    ("paramValue", "0.25"),
                    ("units", "NULL"),
                ]
            ),
            OrderedDict(
                [
                    ("paramName", "kFactor"),
                    ("paramValue", "1.1"),
                    ("units", "NULL"),
                ]
            ),
            OrderedDict(
                [
                    ("paramName", "contactPerson"),
                    ("paramValue", "jsmith"),
                    ("units", "NULL"),
                ]
            ),
        ]
        with patch(
            "ami_mcp.tools.physics.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(dataset="some.dataset.EVNT.e1234", ctx=mock_ctx)

        output = tool_text(result)
        assert "genFiltEff" in output
        assert "0.25" in output
        assert "jsmith" in output

    async def test_returns_no_params_message_on_empty(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = []
        with patch(
            "ami_mcp.tools.physics.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(
                dataset="mc20_13TeV.999999.None.evgen.EVNT.e0000", ctx=mock_ctx
            )

        assert "No physics parameters" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["found"] is False
        assert result.structured_content["params"] == {}

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.physics.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("timeout")),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(dataset="bad.dataset", ctx=mock_ctx)

        output = tool_text(result)
        assert "**Error**:" in output
        assert "EVNT" in output
        assert result.is_error is True

    async def test_non_evnt_shows_warning(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict(
                [
                    ("paramName", "crossSection"),
                    ("paramValue", "1.0"),
                    ("units", "nb"),
                ]
            )
        ]
        with patch(
            "ami_mcp.tools.physics.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_physics_params"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.deriv.DAOD_PHYS.e8351_s3681_p5855",
                ctx=mock_ctx,
            )

        output = tool_text(result)
        assert "Note:" in output
        assert "EVNT" in output
