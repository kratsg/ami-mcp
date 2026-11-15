"""Tests for ami_list_fields."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyAMI.exception
import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.fields import register

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from mcp.types import CallToolResult


@pytest.fixture
def tool_objs() -> dict[str, Any]:
    mcp = MCPServer("test")
    register(mcp)
    return {tool.name: tool for tool in mcp._tool_manager.list_tools()}


class TestAmiListFields:
    def test_declares_read_only_annotations_and_output_schema(
        self, tool_objs: dict[str, Any]
    ) -> None:
        tool = tool_objs["ami_list_fields"]
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is True
        assert tool.output_schema is not None

    async def test_returns_fields_with_type_and_description(
        self,
        tool_objs: dict[str, Any],
        mock_ctx: MagicMock,
        mock_ami_client: MagicMock,
        entity_info_result: Any,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        mock_ami_client.execute.return_value = entity_info_result
        result = await tool_objs["ami_list_fields"].fn(
            project="mc23_13p6TeV", data_type="DAOD_PHYSLITE", ctx=mock_ctx
        )
        assert result.is_error is not True
        structured = result.structured_content
        assert structured["catalog"] == "mc23_001:production"
        assert structured["entity"] == "dataset"
        by_name = {f["name"]: f for f in structured["fields"]}
        assert by_name["datasetNumber"] == {
            "name": "datasetNumber",
            "type": "INT",
            "description": "Dataset number (DSID)",
        }
        assert "datasetNumber" in tool_text(result)

    @pytest.mark.parametrize(
        ("project", "data_type", "catalog"),
        [
            ("mc20_13TeV", "EVNT", "mc15_001:production"),
            ("mc20_13TeV", "DAOD_PHYS", "mc20_001:production"),
            ("mc20_13TeV", None, "mc20_001:production"),
        ],
    )
    async def test_resolves_catalog_like_ami_list_datasets(
        self,
        tool_objs: dict[str, Any],
        mock_ctx: MagicMock,
        mock_ami_client: MagicMock,
        entity_info_result: Any,
        project: str,
        data_type: str | None,
        catalog: str,
    ) -> None:
        mock_ami_client.execute.return_value = entity_info_result
        await tool_objs["ami_list_fields"].fn(
            project=project, data_type=data_type, ctx=mock_ctx
        )
        assert f'-catalog="{catalog}"' in mock_ami_client.execute.call_args.args[0]

    async def test_ami_failure_is_an_error_result(
        self,
        tool_objs: dict[str, Any],
        mock_ctx: MagicMock,
        mock_ami_client: MagicMock,
    ) -> None:
        mock_ami_client.execute.side_effect = pyAMI.exception.Error("pyAMI exception: x")
        result = await tool_objs["ami_list_fields"].fn(
            project="mc23_13p6TeV", ctx=mock_ctx
        )
        assert result.is_error is True
