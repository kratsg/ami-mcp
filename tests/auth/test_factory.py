"""Tests for the AMI client factory indirection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ami_mcp.auth.factory import AmiClientFactory, EnvBasedClientFactory
from ami_mcp.tools._helpers import get_ami_client


class TestAmiClientFactory:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            AmiClientFactory()  # type: ignore[abstract]


class TestEnvBasedClientFactory:
    def test_wraps_shared_client(self) -> None:
        client = MagicMock()
        factory = EnvBasedClientFactory(client=client)
        ctx = MagicMock()
        assert factory.get_client(ctx) is client
        assert factory.get_client(ctx) is client

    def test_endpoint_mode_builds_fresh_client_per_call(self) -> None:
        factory = EnvBasedClientFactory(endpoint="atlas-replica")
        ctx = MagicMock()
        with patch("ami_mcp.auth.factory.pyAMI.client.Client") as client_cls:
            client_cls.side_effect = lambda endpoint: MagicMock(name=endpoint)
            first = factory.get_client(ctx)
            second = factory.get_client(ctx)
        assert first is not second
        assert client_cls.call_count == 2
        client_cls.assert_called_with("atlas-replica")

    def test_requires_exactly_one_of_client_or_endpoint(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            EnvBasedClientFactory()
        with pytest.raises(ValueError, match="exactly one"):
            EnvBasedClientFactory(client=MagicMock(), endpoint="atlas-replica")

    def test_close_is_safe(self) -> None:
        factory = EnvBasedClientFactory(client=MagicMock())
        factory.close()


class TestGetAmiClient:
    def test_returns_client_from_lifespan_factory(self) -> None:
        client = MagicMock()
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {
            "client_factory": EnvBasedClientFactory(client=client)
        }
        assert get_ami_client(ctx) is client
