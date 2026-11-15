from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pyAMI.object
import pytest
from mcp.types import TextContent

from ami_mcp.auth.factory import EnvBasedClientFactory
from ami_mcp.observability import configure_logging
from ami_mcp.policy import DEFAULT_ALLOWED_COMMANDS
from ami_mcp.tools import _schema

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from mcp.types import CallToolResult


@pytest.fixture
def tool_text() -> Callable[[CallToolResult], str]:
    """Return a helper that extracts a tool's CallToolResult's markdown text block.

    Every ami_* tool returns exactly one TextContent block alongside its
    (optional) structured_content -- this is the substring-assertion
    equivalent of the plain-string return the tools used to have.
    """

    def _tool_text(result: CallToolResult) -> str:
        block = result.content[0]
        assert isinstance(block, TextContent)
        return block.text

    return _tool_text


class JsonLog:
    """Everything the root logger wrote as JSON lines since the last ``clear()``."""

    def __init__(self) -> None:
        self.stream = io.StringIO()

    def lines(self) -> list[dict[str, Any]]:
        """Parse each written line; a line that is not JSON fails the test.

        The test client's own request log (loggers ``httpx`` and ``httpx2``) is client-side
        chatter, not the server's output, so it is left out.
        """
        parsed = [json.loads(line) for line in self.stream.getvalue().splitlines()]
        return [line for line in parsed if not line["logger"].startswith("httpx")]

    def clear(self) -> None:
        """Forget what has been written so far."""
        self.stream.truncate(0)
        self.stream.seek(0)


@pytest.fixture
def json_log() -> Iterator[JsonLog]:
    """Route the root logger to a buffer as JSON, restoring it afterwards."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    log = JsonLog()
    configure_logging("info", stream=log.stream)
    yield log
    root.handlers[:] = handlers
    root.setLevel(level)


# (field, type, description) rows of the mc23 dataset entity, in the order AMI's
# GetEntityInfo returns them in its Entity_Fields rowset.
_MC23_DATASET_FIELDS: list[tuple[str, str, str]] = [
    ("identifier", "INT", "Unique identifier"),
    ("logicalDatasetName", "VARCHAR(255)", "Logical dataset name"),
    ("nFiles", "INT", "Number of files"),
    ("totalEvents", "BIGINT", "Total number of events"),
    ("totalSize", "DOUBLE", "Total size in bytes"),
    ("dataType", "VARCHAR(255)", "Data type"),
    ("datasetNumber", "INT", "Dataset number (DSID)"),
    ("physicsShort", "VARCHAR(255)", "Short physics process name"),
    ("amiStatus", "VARCHAR(255)", "AMI status"),
    ("physicsCategory", "VARCHAR(255)", "Physics category"),
    ("jobConfig", "VARCHAR(255)", ""),
    ("crossSection", "DOUBLE", "Cross-section"),
    ("lastModified", "DATETIME", "Last modification date"),
    ("projectName", "VARCHAR(255)", "Project name"),
]


def entity_info_xml(fields: list[tuple[str, str, str]] | None = None) -> str:
    """Build a GetEntityInfo response in the XML shape pyAMI parses.

    The ``table="db_field"`` attribute (with the entity named in ``args``) is
    what makes pyAMI's ``get_rows("Entity_Fields")`` return ``db_field.``-
    prefixed keys, as the live Python API does. Empty columns come back as the
    literal placeholders ``NULL`` / ``empty``.
    """

    def field(name: str, value: str) -> str:
        return f'<field name="{name}" table="db_field">{value}</field>'

    rows = "".join(
        "<row>"
        + field("field", name)
        + field("type", type_)
        + field("description", description or "empty")
        + field("showType", "0")
        + field("family", "main")
        + field("linkClass", "NULL")
        + "</row>"
        for name, type_, description in (fields or _MC23_DATASET_FIELDS)
    )
    return (
        "<?xml version='1.0' encoding='utf-8'?><AMIMessage><command>GetEntityInfo"
        '</command><args argName="entity" argValue="dataset"/><Result>'
        '<rowset type="Entity_Info"><row><field name="entityName">dataset</field>'
        "</row></rowset>"
        f'<rowset type="Entity_Fields">{rows}</rowset>'
        '<rowset type="Entity_Relations"></rowset>'
        "</Result></AMIMessage>"
    )


@pytest.fixture(autouse=True)
def _fresh_schema_cache() -> Iterator[None]:
    """Keep the process-wide entity-schema cache from leaking between tests."""
    _schema.clear_cache()
    yield
    _schema.clear_cache()


# A data-catalog entity (e.g. data24_001:real_data) has no `identifier` field.
_DATA_DATASET_FIELDS = [
    f for f in _MC23_DATASET_FIELDS if f[0] != "identifier" and f[0] != "crossSection"
]


@pytest.fixture
def data_entity_info_result() -> pyAMI.object.DOMObject:
    """Return a GetEntityInfo DOMObject for a data catalog (no `identifier`)."""
    return pyAMI.object.DOMObject(entity_info_xml(_DATA_DATASET_FIELDS))


@pytest.fixture
def entity_info_result() -> pyAMI.object.DOMObject:
    """Return a real pyAMI DOMObject parsed from a recorded-shape GetEntityInfo."""
    return pyAMI.object.DOMObject(entity_info_xml())


@pytest.fixture
def mock_ami_client() -> MagicMock:
    """Return a MagicMock that mimics pyAMI.client.Client."""
    client = MagicMock()
    result_mock = MagicMock()
    result_mock.get_rows.return_value = []
    client.execute.return_value = result_mock
    return client


@pytest.fixture
def mock_ctx(mock_ami_client: MagicMock) -> MagicMock:
    """Return a mock MCPServer Context with a client factory in lifespan context."""
    ctx: MagicMock = MagicMock()
    ctx.request_context.lifespan_context = {
        "client_factory": EnvBasedClientFactory(client=mock_ami_client),
        "allowed_commands": DEFAULT_ALLOWED_COMMANDS,
    }
    return ctx


def pytest_addoption(parser: Any) -> None:
    """Add command line options for test categories."""
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    """Skip tests based on command line options."""
    if not config.getoption("--runslow"):
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
