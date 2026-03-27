from __future__ import annotations

import importlib.metadata

import ami_mcp as m


def test_version() -> None:
    assert importlib.metadata.version("ami-mcp") == m.__version__
