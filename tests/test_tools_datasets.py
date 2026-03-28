"""Tests for dataset info tools."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.datasets import register

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@pytest.fixture
def registered_tools() -> dict[str, Callable[..., Awaitable[str]]]:
    mcp = FastMCP("test")
    register(mcp)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


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
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = _make_result_mock(_DATASET_ROWS)
        with patch(
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351", ctx=mock_ctx
            )

        assert "VALID" in result
        assert "10000" in result

    async def test_returns_error_on_exception(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        with patch(
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(side_effect=RuntimeError("network error")),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(dataset="bad.dataset", ctx=mock_ctx)

        assert "Error" in result


class TestAmiGetDatasetProv:
    async def test_returns_provenance(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
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
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh.deriv.DAOD_PHYS.e8351_p5855", ctx=mock_ctx
            )

        assert "Nodes" in result
        assert "parent.EVNT" in result

    async def test_no_provenance_message(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[str]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = _make_result_mock([], node_rows=[], edge_rows=[])
        with patch(
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="some.dataset", ctx=mock_ctx)

        assert "No provenance" in result

    async def test_basic_chain(self, registered_tools, mock_ctx):
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
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="some.dataset", ctx=mock_ctx)

        assert "## Lineage Summary" in result
        assert "EVNT → HITS → AOD" in result
        assert "## Nodes" in result
        assert "parent.EVNT" in result
        assert "child.HITS" in result
        assert "grandchild.AOD" in result
        assert "## Edges" in result
        # check table formatting
        assert "| source | destination |" in result
        assert "parent.EVNT" in result
        assert "child.HITS" in result

    async def test_data_types_filter_exact(self, registered_tools, mock_ctx):
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
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", data_types="EVNT", ctx=mock_ctx)

        assert "HITS" not in result
        assert "EVNT" in result
        assert "No nodes remain after filtering" not in result

    async def test_data_types_filter_prefix(self, registered_tools, mock_ctx):
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
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", data_types="DAOD_", ctx=mock_ctx)

        # Only DAOD_PHYS and DAOD_FTAG1 should appear
        assert "DAOD_PHYS" in result
        assert "DAOD_FTAG1" in result
        assert ".AOD" not in result

    async def test_no_nodes_found(self, registered_tools, mock_ctx):
        result_mock = _make_result_mock([])
        with patch(
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", ctx=mock_ctx)
        assert "No provenance found." in result

    async def test_edge_pruning_after_filter(self, registered_tools, mock_ctx):
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
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", data_types="EVNT", ctx=mock_ctx)

        # Edge between EVNT → HITS should be removed after filtering
        assert "HITS" not in result
        assert "## Edges" not in result

    async def test_multiple_nodes_same_distance(self, registered_tools, mock_ctx):
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
            "ami_mcp.tools.datasets.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_prov"]
            result = await fn(dataset="ds", ctx=mock_ctx)

        # Should show same-distance nodes in parentheses and sorted alphanumerically
        assert "(HEPMC, HITS)" in result or "(HITS, HEPMC)" in result
        assert "## Nodes" in result
