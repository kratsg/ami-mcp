"""Tests for dataset info tools."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from ami_mcp.tools.datasets import _DATASET_INFO_FIELDS, register

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
        [
            "ami_get_dataset_info",
            "ami_get_dataset_prov",
            "ami_list_datasets",
            "ami_get_datasets_info",
        ],
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
        [
            "ami_get_dataset_info",
            "ami_get_dataset_prov",
            "ami_list_datasets",
            "ami_get_datasets_info",
        ],
    )
    def test_publishes_an_output_schema(
        self, registered_tool_objs: dict[str, Any], name: str
    ) -> None:
        assert registered_tool_objs[name].output_schema is not None

    def test_single_dataset_tool_description_steers_to_batch_tool(
        self, registered_tool_objs: dict[str, Any]
    ) -> None:
        assert (
            "ami_get_datasets_info"
            in registered_tool_objs["ami_get_dataset_info"].description
        )


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
            ("totalEvents", "10000"),
            ("amiStatus", "VALID"),
            ("productionStep", "evgen"),
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

    async def test_total_events_and_production_step_survive_the_field_filter(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        """totalEvents/productionStep are AMI's real dataset field names --
        confirm _DATASET_INFO_FIELDS keeps them rather than silently dropping
        them (as the old nEvents/prodStep names did, since AMI never returns
        rows keyed by those names)."""
        result_mock = _make_result_mock(_DATASET_ROWS)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_get_dataset_info"]
            result = await fn(
                dataset="mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351", ctx=mock_ctx
            )

        assert result.structured_content is not None
        fields = result.structured_content["fields"]
        assert fields["totalEvents"] == "10000"
        assert fields["productionStep"] == "evgen"

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

    async def test_returns_structured_content_with_rows(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        rows = [
            OrderedDict(
                [
                    (
                        "logicalDatasetName",
                        "mc20_13TeV.700320.Sh_2211_Zee.deriv.DAOD_PHYS.e8351_p5855",
                    ),
                    ("physicsShort", "Sh_2211_Zee"),
                    ("amiStatus", "VALID"),
                ]
            )
        ]
        result_mock = _make_result_mock(rows)
        with patch(
            "ami_mcp.tools.datasets.run_ami_command",
            new=AsyncMock(return_value=result_mock),
        ):
            fn = registered_tools["ami_list_datasets"]
            result = await fn(
                patterns="%Zee%",
                project="mc20_13TeV",
                data_type="DAOD_PHYS",
                ctx=mock_ctx,
            )

        output = tool_text(result)
        assert "Sh_2211_Zee" in output
        assert result.is_error is not True
        assert result.structured_content is not None
        assert result.structured_content["catalog"] == "mc20_001:production"
        assert result.structured_content["ami_status"] == "VALID"
        assert result.structured_content["total"] == 1
        assert result.structured_content["rows"][0]["physicsShort"] == "Sh_2211_Zee"


class TestAmiListDatasetsCatalogSelection:
    @pytest.mark.parametrize(
        ("project", "data_type", "expected_catalog"),
        [
            # The exact #24 repro: mc20 derivation must search mc20's own
            # catalog, not the evgen-only mc15 catalog.
            ("mc20_13TeV", "DAOD_PHYSLITE", "mc20_001:production"),
            ("mc20_13TeV", "DAOD_PHYS", "mc20_001:production"),
            ("mc20_13TeV", "AOD", "mc20_001:production"),
            ("mc20_13TeV", None, "mc20_001:production"),
            ("mc20_13TeV", "EVNT", "mc15_001:production"),
            ("mc20_13TeV", "HITS", "mc16_001:production"),
            ("mc16_13TeV", "EVNT", "mc15_001:production"),
            ("mc16_13TeV", "AOD", "mc16_001:production"),
            ("mc23_13p6TeV", "EVNT", "mc23_001:production"),
            ("mc23_13p6TeV", "DAOD_PHYS", "mc23_001:production"),
        ],
    )
    async def test_selects_catalog_by_project_and_data_type(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        project: str,
        data_type: str | None,
        expected_catalog: str,
    ) -> None:
        result_mock = _make_result_mock([])
        executed_commands: list[str] = []

        async def capture(_func, *args, **_kwargs):
            executed_commands.append(str(args[0]))
            return result_mock

        with patch("ami_mcp.tools.datasets.run_ami_command", new=capture):
            fn = registered_tools["ami_list_datasets"]
            await fn(
                patterns="%Zee%", project=project, data_type=data_type, ctx=mock_ctx
            )

        assert f"-catalog={expected_catalog}" in executed_commands[0]

    async def test_ami_status_default_is_valid(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = _make_result_mock([])
        executed_commands: list[str] = []

        async def capture(_func, *args, **_kwargs):
            executed_commands.append(str(args[0]))
            return result_mock

        with patch("ami_mcp.tools.datasets.run_ami_command", new=capture):
            fn = registered_tools["ami_list_datasets"]
            await fn(patterns="%Zee%", project="mc20_13TeV", ctx=mock_ctx)

        assert "amiStatus = 'VALID'" in executed_commands[0]

    async def test_ami_status_none_omits_status_filter(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        result_mock = _make_result_mock([])
        executed_commands: list[str] = []

        async def capture(_func, *args, **_kwargs):
            executed_commands.append(str(args[0]))
            return result_mock

        with patch("ami_mcp.tools.datasets.run_ami_command", new=capture):
            fn = registered_tools["ami_list_datasets"]
            await fn(
                patterns="%Zee%",
                project="mc20_13TeV",
                ami_status=None,
                ctx=mock_ctx,
            )

        # amiStatus is still SELECTed (a display column); it must simply not
        # appear as a WHERE condition.
        assert "amiStatus =" not in executed_commands[0]

    async def test_empty_result_hints_name_catalog_and_status(
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
            fn = registered_tools["ami_list_datasets"]
            result = await fn(
                patterns="%Zee%",
                project="mc20_13TeV",
                data_type="DAOD_PHYSLITE",
                ctx=mock_ctx,
            )

        output = tool_text(result)
        assert "mc20_001:production" in output
        assert "VALID" in output
        assert 'data_type="EVNT"' in output
        assert result.structured_content is not None
        assert result.structured_content["catalog"] == "mc20_001:production"
        assert result.structured_content["total"] == 0


def _make_catalog_router(
    catalog_rows: dict[str, list[Any]], executed_commands: list[str]
) -> Callable[..., Any]:
    """Return a ``run_ami_command`` stand-in that routes by the command's ``-catalog=``.

    Records every issued command (so a test can assert exactly how many AMI
    commands were run, and against which catalogs) and returns the rows
    configured for that catalog, mimicking a per-catalog SearchQuery result.
    """

    async def _router(_ctx: Any, command: str, **_kwargs: Any) -> Any:
        executed_commands.append(command)
        catalog = command.split("-catalog=", 1)[1].split(" ", 1)[0]
        return _make_result_mock(catalog_rows.get(catalog, []))

    return _router


class TestAmiGetDatasetsInfo:
    async def test_single_catalog_all_found_issues_one_command(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        ds1 = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"
        ds2 = "mc20_13TeV.700321.Sh_2211_Zmumu.evgen.EVNT.e8351"
        # AMI row order is arbitrary (ds2 before ds1 here, opposite of the
        # input order) and rows carry AMI bookkeeping keys alongside the real
        # dataset fields -- both must be handled: input order preserved in
        # the results, bookkeeping keys stripped from `fields`.
        rows = [
            OrderedDict(
                [
                    ("logicalDatasetName", ds2),
                    ("nFiles", "20"),
                    ("totalEvents", "2000"),
                    ("amiStatus", "VALID"),
                    ("PROJECT", "mc20_001"),
                    ("PROCESS", "dataset"),
                    ("AMIENTITYNAME", "dataset"),
                    ("AMIELEMENTID", "222"),
                ]
            ),
            OrderedDict(
                [
                    ("logicalDatasetName", ds1),
                    ("nFiles", "10"),
                    ("totalEvents", "1000"),
                    ("amiStatus", "VALID"),
                    ("PROJECT", "mc20_001"),
                    ("PROCESS", "dataset"),
                    ("AMIENTITYNAME", "dataset"),
                    ("AMIELEMENTID", "111"),
                ]
            ),
        ]
        executed_commands: list[str] = []
        router = _make_catalog_router({"mc15_001:production": rows}, executed_commands)

        with patch("ami_mcp.tools.datasets.run_ami_command", new=router):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=[ds1, ds2], ctx=mock_ctx)

        # Both LDNs share a catalog (mc20_13TeV evgen -> mc15_001:production),
        # so this must collapse to a single AMI command.
        assert len(executed_commands) == 1
        assert "IN (" in executed_commands[0]
        assert ds1 in executed_commands[0]
        assert ds2 in executed_commands[0]

        assert result.is_error is not True
        payload = result.structured_content
        assert payload is not None
        assert payload["requested"] == 2
        assert payload["found"] == 2
        # Results come back in the order requested, not AMI's row order.
        assert [r["dataset"] for r in payload["results"]] == [ds1, ds2]
        assert all(r["found"] for r in payload["results"])
        assert payload["results"][0]["fields"]["amiStatus"] == "VALID"
        assert payload["results"][0]["fields"]["totalEvents"] == "1000"
        assert payload["results"][1]["fields"]["totalEvents"] == "2000"
        # AMI bookkeeping keys are filtered out the same way
        # ami_get_dataset_info filters them (allowlist against
        # _DATASET_INFO_FIELDS), not just the real dataset fields.
        for entry in payload["results"]:
            for bookkeeping_key in (
                "PROJECT",
                "PROCESS",
                "AMIENTITYNAME",
                "AMIELEMENTID",
            ):
                assert bookkeeping_key not in entry["fields"]

    async def test_mixed_found_and_not_found(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        found_ds = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"
        missing_ds = "mc20_13TeV.999999.NoSuchSample.evgen.EVNT.e0000"
        rows = [OrderedDict([("logicalDatasetName", found_ds), ("nFiles", "10")])]
        executed_commands: list[str] = []
        router = _make_catalog_router({"mc15_001:production": rows}, executed_commands)

        with patch("ami_mcp.tools.datasets.run_ami_command", new=router):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=[found_ds, missing_ds], ctx=mock_ctx)

        payload = result.structured_content
        assert payload is not None
        assert payload["requested"] == 2
        assert payload["found"] == 1
        by_ds = {r["dataset"]: r for r in payload["results"]}
        assert by_ds[found_ds]["found"] is True
        assert by_ds[missing_ds]["found"] is False
        assert by_ds[missing_ds]["error"] is None
        assert missing_ds in tool_text(result)

    async def test_cross_catalog_grouping_issues_one_command_per_catalog(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        # evgen EVNT -> mc15_001:production; deriv DAOD_PHYS -> mc20_001:production
        # (see scope_to_catalog()/#28's project+prod-step catalog selection).
        evgen_ds = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"
        deriv_ds = "mc20_13TeV.700320.Sh_2211_Zee.deriv.DAOD_PHYS.e8351_p5855"
        rows_by_catalog = {
            "mc15_001:production": [
                OrderedDict([("logicalDatasetName", evgen_ds), ("nFiles", "1")])
            ],
            "mc20_001:production": [
                OrderedDict([("logicalDatasetName", deriv_ds), ("nFiles", "2")])
            ],
        }
        executed_commands: list[str] = []
        router = _make_catalog_router(rows_by_catalog, executed_commands)

        with patch("ami_mcp.tools.datasets.run_ami_command", new=router):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=[evgen_ds, deriv_ds], ctx=mock_ctx)

        assert len(executed_commands) == 2
        catalogs_queried = {
            cmd.split("-catalog=", 1)[1].split(" ", 1)[0] for cmd in executed_commands
        }
        assert catalogs_queried == {"mc15_001:production", "mc20_001:production"}
        payload = result.structured_content
        assert payload is not None
        assert payload["found"] == 2
        by_ds = {r["dataset"]: r for r in payload["results"]}
        assert by_ds[evgen_ds]["found"] is True
        assert by_ds[deriv_ds]["found"] is True

    async def test_cap_exceeded_returns_error_without_querying_ami(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        too_many = [f"mc20_13TeV.{i}.Sample.evgen.EVNT.e0000" for i in range(51)]
        mock_run = AsyncMock()

        with patch("ami_mcp.tools.datasets.run_ami_command", new=mock_run):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=too_many, ctx=mock_ctx)

        assert result.is_error is True
        assert "50" in tool_text(result)
        assert mock_run.await_count == 0

    async def test_duplicate_input_is_deduped(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        ds = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"
        rows = [OrderedDict([("logicalDatasetName", ds), ("nFiles", "1")])]
        executed_commands: list[str] = []
        router = _make_catalog_router({"mc15_001:production": rows}, executed_commands)

        with patch("ami_mcp.tools.datasets.run_ami_command", new=router):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=[ds, ds, ds], ctx=mock_ctx)

        assert executed_commands[0].count(ds) == 1
        payload = result.structured_content
        assert payload is not None
        assert payload["requested"] == 1
        assert len(payload["results"]) == 1

    async def test_malformed_ldn_gets_a_per_dataset_error_without_querying_ami(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
        tool_text: Callable[[CallToolResult], str],
    ) -> None:
        bad = "not-a-valid-ldn"
        mock_run = AsyncMock()

        with patch("ami_mcp.tools.datasets.run_ami_command", new=mock_run):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=[bad], ctx=mock_ctx)

        assert mock_run.await_count == 0
        payload = result.structured_content
        assert payload is not None
        assert payload["results"][0]["found"] is False
        assert payload["results"][0]["error"]
        assert bad in tool_text(result)

    async def test_catalog_query_failure_is_scoped_to_that_catalogs_datasets(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        evgen_ds = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"  # mc15_001
        deriv_ds = (
            "mc20_13TeV.700320.Sh_2211_Zee.deriv.DAOD_PHYS.e8351_p5855"  # mc20_001
        )

        async def _router(_ctx: Any, command: str, **_kwargs: Any) -> Any:
            if "mc15_001:production" in command:
                msg = (
                    "pyAMI exception: Max command frequency reached for this "
                    "user/machine."
                )
                raise RuntimeError(msg)
            return _make_result_mock(
                [OrderedDict([("logicalDatasetName", deriv_ds), ("nFiles", "2")])]
            )

        with patch("ami_mcp.tools.datasets.run_ami_command", new=_router):
            fn = registered_tools["ami_get_datasets_info"]
            result = await fn(datasets=[evgen_ds, deriv_ds], ctx=mock_ctx)

        payload = result.structured_content
        assert payload is not None
        by_ds = {r["dataset"]: r for r in payload["results"]}
        assert by_ds[evgen_ds]["found"] is False
        assert "frequency" in by_ds[evgen_ds]["error"].lower()
        assert by_ds[deriv_ds]["found"] is True
        assert by_ds[deriv_ds]["error"] is None

    async def test_select_list_matches_dataset_info_fields(
        self,
        registered_tools: dict[str, Callable[..., Awaitable[CallToolResult]]],
        mock_ctx: MagicMock,
    ) -> None:
        """Regression guard: AMI's SearchQuery silently returns zero rows (no
        error) when the SELECT list names an unknown field, so a SELECT list
        that drifts from _DATASET_INFO_FIELDS -- e.g. reintroducing the old
        nEvents/prodStep/kFactor names -- would fail every lookup in the
        batch without a single error to point at."""
        ds = "mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"
        executed_commands: list[str] = []
        router = _make_catalog_router({"mc15_001:production": []}, executed_commands)

        with patch("ami_mcp.tools.datasets.run_ami_command", new=router):
            fn = registered_tools["ami_get_datasets_info"]
            await fn(datasets=[ds], ctx=mock_ctx)

        assert len(executed_commands) == 1
        select_clause = (
            executed_commands[0].split("SELECT ", 1)[1].split(" WHERE", 1)[0]
        )
        selected_fields = [f.strip() for f in select_clause.split(",")]
        assert selected_fields == _DATASET_INFO_FIELDS
        assert "nEvents" not in selected_fields
        assert "prodStep" not in selected_fields
        assert "kFactor" not in selected_fields
