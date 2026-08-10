"""Tests for the AMI client factory indirection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ami_mcp.auth.factory import AmiClientFactory, EnvBasedClientFactory
from ami_mcp.tools._helpers import run_ami_command


class TestAmiClientFactory:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            AmiClientFactory()  # type: ignore[abstract]


class TestEnvBasedClientFactory:
    async def test_wraps_shared_client(self) -> None:
        client = MagicMock()
        factory = EnvBasedClientFactory(client=client)
        ctx = MagicMock()
        async with factory.get_client(ctx) as first:
            assert first is client
        async with factory.get_client(ctx) as second:
            assert second is client

    async def test_endpoint_mode_builds_fresh_client_per_call(self) -> None:
        factory = EnvBasedClientFactory(endpoint="atlas-replica")
        ctx = MagicMock()
        with patch("ami_mcp.auth.factory.pyAMI.client.Client") as client_cls:
            client_cls.side_effect = lambda endpoint: MagicMock(name=endpoint)
            async with factory.get_client(ctx) as first:
                pass
            async with factory.get_client(ctx) as second:
                pass
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


class TestRunAmiCommand:
    async def test_executes_via_lifespan_factory(self) -> None:
        client = MagicMock()
        expected = MagicMock()
        client.execute.return_value = expected
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {
            "client_factory": EnvBasedClientFactory(client=client)
        }

        result = await run_ami_command(ctx, 'AMIGetDatasetInfo -logicalDatasetName="x"')

        assert result is expected
        client.execute.assert_called_once_with(
            'AMIGetDatasetInfo -logicalDatasetName="x"', format="dom_object"
        )
