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
            OrderedDict([("logicalDatasetName", "parent.evnt"), ("distance", "1")])
        ]
        edges = [OrderedDict([("input", "parent.evnt"), ("output", "child.hits")])]
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
        assert "parent.evnt" in result

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
