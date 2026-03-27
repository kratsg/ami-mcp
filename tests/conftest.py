from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


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
    """Return a mock FastMCP Context with an ami_client in lifespan context."""
    ctx: MagicMock = MagicMock()
    ctx.request_context.lifespan_context = {"ami_client": mock_ami_client}
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
