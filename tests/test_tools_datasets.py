"""Tests for dataset info tools."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.datasets import register

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


class TestDatasetsToolRegistration:
    @pytest.mark.parametrize(
        "name",
        ["ami_get_dataset_info", "ami_get_dataset_prov", "ami_list_datasets"],
    )
    def test_declares_read_only_annotations(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        tool = registered_tool_objs[name]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is True

    @pytest.mark.parametrize(
        "name",
        ["ami_get_dataset_info", "ami_get_dataset_prov", "ami_list_datasets"],
    )
    def test_publishes_an_output_schema(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        assert registered_tool_objs[name].output_schema is not None


def _make_result_mock(
    rows: list[Any],
    node_rows: list[Any] | None = None,
    edge_rows: list[Any] | None = None,
) -> MagicMock:
    """Return a mock DOMObject whose get_rows() returns the given rows."""
    result_mock = MagicMock()

    def get_rows(row_type: str | None = None) -> list[Any]:
        if row_type == "node":
            return node_rows or []
        if row_type == "edge":
            return edge_rows or []
        return rows

    result_mock.get_rows.side_effect = get_rows
    return result_mock


_DATASET_ROWS = [
    OrderedDict(
        [
            ("logicalDatasetName", "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"),
            ("nFiles", "42"),
            ("nEvents", "10000"),
            ("amiStatus", "VALID"),
        ]
    )
]


class TestAmiGetDatasetInfo:
    async def test_returns_dataset_fields(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = _make_result_mock(_DATASET_ROWS)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351", ctx=mock_ctx
            )

        output = tool_text(result)
        assert "VALID" in output
        assert "10000" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        assert result.structured_content["found"] is True
        assert result.structured_content["fields"]["amiStatus"] == "VALID"

    async def test_no_results(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = _make_result_mock([])
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(dataset="missing.dataset", ctx=mock_ctx)

        assert "No results." in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["found"] is False
        assert result.structured_content["fields"] == {}

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("network error")),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(dataset="bad.dataset", ctx=mock_ctx)

        assert "Error" in tool_text(result)
        assert result.is_error is True
        assert result.structured_content is None


class TestAmiGetDatasetProv:
    async def test_returns_provenance(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        nodes = [
            OrderedDict(
                [
                    ("logicalDatasetName", "parent.EVNT"),
                    ("dataType", "EVNT"),
                    ("distance", 1),
                    ("events", 1000),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "child.HITS"),
                    ("dataType", "HITS"),
                    ("distance", 2),
                    ("events", 100),
                ]
            ),
        ]
        edges = [
            OrderedDict([("source", "parent.EVNT"), ("destination", "child.HITS")])
        ]
        result_mock = _make_result_mock([], node_rows=nodes, edge_rows=edges)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.deriv.DAOD_PHYS.e8351_p5855", ctx=mock_ctx
            )

        output = tool_text(result)
        assert "Nodes" in output
        assert "parent.EVNT" in output
        assert result.structured_content is not None
        assert result.structured_content["found"] is True
        assert len(result.structured_content["nodes"]) == 2
        assert len(result.structured_content["edges"]) == 1

    async def test_no_provenance_message(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        result_mock = _make_result_mock([], node_rows=[], edge_rows=[])
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="some.dataset", ctx=mock_ctx)

        assert "No provenance" in tool_text(result)
        assert result.structured_content is not None
        assert result.structured_content["found"] is False

    async def test_basic_chain(self, registered_tools, mock_ctx, tool_text):
        nodes = [
            OrderedDict(
                [
                    ("logicalDatasetName", "parent.EVNT"),
                    ("dataType", "EVNT"),
                    ("distance", 0),
                    ("events", 1000),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "child.HITS"),
                    ("dataType", "HITS"),
                    ("distance", 1),
                    ("events", 100),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "grandchild.AOD"),
                    ("dataType", "AOD"),
                    ("distance", 2),
                    ("events", 50),
                ]
            ),
        ]
        edges = [
            OrderedDict([("source", "parent.EVNT"), ("destination", "child.HITS")]),
            OrderedDict([("source", "child.HITS"), ("destination", "grandchild.AOD")]),
        ]
        result_mock = _make_result_mock([], nodes, edges)

        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="some.dataset", ctx=mock_ctx)

        output = tool_text(result)
        assert "## Lineage Summary" in output
        assert "EVNT → HITS → AOD" in output
        assert "## Nodes" in output
        assert "parent.EVNT" in output
        assert "child.HITS" in output
        assert "grandchild.AOD" in output
        assert "## Edges" in output
        # check table formatting
        assert "| source | destination |" in output
        assert "parent.EVNT" in output
        assert "child.HITS" in output
        assert result.structured_content["summary"] == "EVNT → HITS → AOD"

    async def test_data_types_filter_exact(self, registered_tools, mock_ctx, tool_text):
        nodes = [
            OrderedDict(
                [
                    ("logicalDatasetName", "n1.EVNT"),
                    ("dataType", "EVNT"),
                    ("distance", 0),
                    ("events", 100),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "n2.HITS"),
                    ("dataType", "HITS"),
                    ("distance", 1),
                    ("events", 50),
                ]
            ),
        ]
        edges = [OrderedDict([("source", "n1.EVNT"), ("destination", "n2.HITS")])]
        result_mock = _make_result_mock([], nodes, edges)

        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", data_types="EVNT", ctx=mock_ctx)

        output = tool_text(result)
        assert "HITS" not in output
        assert "EVNT" in output
        assert "No nodes remain after filtering" not in output

    async def test_data_types_filter_prefix(
        self, registered_tools, mock_ctx, tool_text
    ):
        nodes = [
            OrderedDict(
                [
                    ("logicalDatasetName", "d1.DAOD_PHYS"),
                    ("dataType", "DAOD_PHYS"),
                    ("distance", 0),
                    ("events", 1000),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "d2.DAOD_FTAG1"),
                    ("dataType", "DAOD_FTAG1"),
                    ("distance", 1),
                    ("events", 500),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "d3.AOD"),
                    ("dataType", "AOD"),
                    ("distance", 2),
                    ("events", 100),
                ]
            ),
        ]
        edges = [
            OrderedDict([("source", "d1.DAOD_PHYS"), ("destination", "d2.DAOD_FTAG1")]),
            OrderedDict([("source", "d2.DAOD_FTAG1"), ("destination", "d3.AOD")]),
        ]
        result_mock = _make_result_mock([], nodes, edges)

        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", data_types="DAOD_", ctx=mock_ctx)

        output = tool_text(result)
        # Only DAOD_PHYS and DAOD_FTAG1 should appear
        assert "DAOD_PHYS" in output
        assert "DAOD_FTAG1" in output
        assert ".AOD" not in output

    async def test_no_nodes_found(self, registered_tools, mock_ctx, tool_text):
        result_mock = _make_result_mock([])
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", ctx=mock_ctx)
        assert "No provenance found." in tool_text(result)

    async def test_edge_pruning_after_filter(
        self, registered_tools, mock_ctx, tool_text
    ):
        nodes = [
            OrderedDict(
                [
                    ("logicalDatasetName", "n1.EVNT"),
                    ("dataType", "EVNT"),
                    ("distance", 0),
                    ("events", 100),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "n2.HITS"),
                    ("dataType", "HITS"),
                    ("distance", 1),
                    ("events", 50),
                ]
            ),
        ]
        edges = [OrderedDict([("source", "n1.EVNT"), ("destination", "n2.HITS")])]
        result_mock = _make_result_mock([], nodes, edges)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", data_types="EVNT", ctx=mock_ctx)

        output = tool_text(result)
        # Edge between EVNT → HITS should be removed after filtering
        assert "HITS" not in output
        assert "## Edges" not in output
        assert result.structured_content["edges"] == []

    async def test_multiple_nodes_same_distance(
        self, registered_tools, mock_ctx, tool_text
    ):
        nodes = [
            OrderedDict(
                [
                    ("logicalDatasetName", "n1.EVNT"),
                    ("dataType", "EVNT"),
                    ("distance", 0),
                    ("events", 100),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "n2.HITS"),
                    ("dataType", "HITS"),
                    ("distance", 1),
                    ("events", 50),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", "n3.HEPMC"),
                    ("dataType", "HEPMC"),
                    ("distance", 1),
                    ("events", 25),
                ]
            ),
        ]
        edges: list[dict[str, str]] = []
        result_mock = _make_result_mock([], nodes, edges)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", ctx=mock_ctx)

        output = tool_text(result)
        # Should show same-distance nodes in parentheses and sorted alphanumerically
        assert "(HEPMC, HITS)" in output or "(HITS, HEPMC)" in output
        assert "## Nodes" in output


class TestAmiGetDatasetInfoContextualHints:
    async def test_trashed_dataset_hint(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        rows = [
            OrderedDict(
                [
                    ("logicalDatasetName", "mc20_13TeV.700320.Sh.evgen.EVNT.e8351"),
                    ("nFiles", "0"),
                    ("amiStatus", "TRASHED"),
                ]
            )
        ]
        result_mock = _make_result_mock(rows)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        output = tool_text(result)
        assert "TRASHED" in output
        assert "newer version" in output

    async def test_nfiles_zero_hint(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        rows = [
            OrderedDict(
                [
                    ("logicalDatasetName", "mc20_13TeV.700320.Sh.evgen.EVNT.e8351"),
                    ("nFiles", "0"),
                    ("amiStatus", "VALID"),
                ]
            )
        ]
        result_mock = _make_result_mock(rows)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.evgen.EVNT.e8351", ctx=mock_ctx
            )

        assert "nFiles=0" in tool_text(result)


class TestAmiListDatasets:
    async def test_builds_correct_command_with_wildcards(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        """Command must not double-quote catalog/entity and must use LIMIT 0,N syntax."""
        result_mock = _make_result_mock([])
        executed_commands: list[str] = []

        async def capture(_func, *args, **_kwargs):
            executed_commands.append(str(args[0]))
            return result_mock

        with patch("ami_mcp.tools.datasets.run_ami_command", new=capture):
            fn = registered_tools["ami_list_datasets"]
            await fn(patterns="%Zee%", project="mc23_13p6TeV", ctx=mock_ctx)

        assert len(executed_commands) == 1
        cmd = executed_commands[0]
        # Catalog must not be double-quoted (would break % wildcards)
        assert "-catalog=mc23_001:production" in cmd
        assert "-entity=dataset" in cmd
        # LIMIT syntax must be LIMIT 0,N not LIMIT N
        assert "LIMIT 0," in cmd
        # Wildcard must be preserved in the MQL
        assert "%Zee%" in cmd

    async def test_returns_error_with_hints(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(side_effect=RuntimeError("parse error")),
        ):
            fn = registered_tools["ami_list_datasets"]
            result = await fn(patterns="%Zee%", project="mc23_13p6TeV", ctx=mock_ctx)

        output = tool_text(result)
        assert "**Error**:" in output
        assert "wildcard" in output.lower() or "%" in output
        assert result.is_error is True
