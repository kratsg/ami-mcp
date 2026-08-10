"""Tests for broker mode: bearer extraction and the proxy-backed factory."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import mkstemp
from unittest.mock import MagicMock, patch

import pytest

af_credentials = pytest.importorskip("af_credentials")

from af_credentials.proxy import (
    ProxyHandle,
    ProxyNotAvailableError,
)

from ami_mcp.auth.broker import (
    BrokerProxyClientFactory,
    extract_bearer,
)


def _make_ctx(headers: dict[str, str]) -> MagicMock:
    ctx = MagicMock()
    ctx.request_context.request.headers = headers
    return ctx


def _utc_soon() -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(hours=1)


class _FakeProxyClient:
    """Duck-typed stand-in for af_credentials.proxy.ProxyClient."""

    def __init__(self) -> None:
        self.seen_bearers: list[str] = []
        self.created_paths: list[Path] = []

    async def proxy_file(self, bearer: str) -> ProxyHandle:
        self.seen_bearers.append(bearer)
        fd, raw_path = mkstemp(prefix="test-proxy-", suffix=".pem")
        os.close(fd)
        path = Path(raw_path)
        path.write_text("FAKE PEM")
        self.created_paths.append(path)
        return ProxyHandle(path=path, dn="/CN=test", expires_at=_utc_soon())


class _UnavailableProxyClient:
    async def proxy_file(self, _bearer: str) -> ProxyHandle:
        detail = "no valid proxy — mint one at the portal"
        raise ProxyNotAvailableError(detail)


class TestExtractBearer:
    def test_returns_token(self) -> None:
        ctx = _make_ctx({"authorization": "Bearer abc123"})
        assert extract_bearer(ctx) == "abc123"

    def test_case_insensitive_scheme(self) -> None:
        ctx = _make_ctx({"authorization": "bearer abc123"})
        assert extract_bearer(ctx) == "abc123"

    def test_missing_header_raises(self) -> None:
        ctx = _make_ctx({})
        with pytest.raises(PermissionError, match="Bearer"):
            extract_bearer(ctx)

    def test_non_bearer_scheme_raises(self) -> None:
        ctx = _make_ctx({"authorization": "Basic dXNlcjpwYXNz"})
        with pytest.raises(PermissionError, match="Bearer"):
            extract_bearer(ctx)


class TestBrokerProxyClientFactory:
    async def test_client_backed_by_redeemed_proxy_file(self) -> None:
        proxy_client = _FakeProxyClient()
        factory = BrokerProxyClientFactory(proxy_client, endpoint="atlas-replica")
        ctx = _make_ctx({"authorization": "Bearer tok"})

        with patch("ami_mcp.auth.broker.pyAMI.client.Client") as client_cls:
            async with factory.get_client(ctx) as client:
                assert client is client_cls.return_value
                (endpoint,), kwargs = client_cls.call_args
                assert endpoint == "atlas-replica"
                proxy_path = Path(kwargs["key_file"])
                assert kwargs["cert_file"] == kwargs["key_file"]
                assert proxy_path.read_text() == "FAKE PEM"

        # The never-persist rule: the proxy file is gone after the call.
        assert not proxy_path.exists()
        assert proxy_client.seen_bearers == ["tok"]

    async def test_proxy_file_deleted_on_error_inside_block(self) -> None:
        proxy_client = _FakeProxyClient()
        factory = BrokerProxyClientFactory(proxy_client, endpoint="atlas-replica")
        ctx = _make_ctx({"authorization": "Bearer tok"})

        async def _fail_mid_call() -> None:
            async with factory.get_client(ctx):
                msg = "boom"
                raise RuntimeError(msg)

        with (
            patch("ami_mcp.auth.broker.pyAMI.client.Client"),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await _fail_mid_call()

        assert not proxy_client.created_paths[0].exists()

    async def test_proxy_not_available_propagates(self) -> None:
        factory = BrokerProxyClientFactory(
            _UnavailableProxyClient(), endpoint="atlas-replica"
        )
        ctx = _make_ctx({"authorization": "Bearer tok"})

        with pytest.raises(ProxyNotAvailableError, match="mint one at the portal"):
            async with factory.get_client(ctx):
                pass

    async def test_missing_bearer_raises_before_redeem(self) -> None:
        proxy_client = _FakeProxyClient()
        factory = BrokerProxyClientFactory(proxy_client, endpoint="atlas-replica")
        ctx = _make_ctx({})

        with pytest.raises(PermissionError):
            async with factory.get_client(ctx):
                pass
        assert proxy_client.seen_bearers == []

    def test_close_is_safe(self) -> None:
        factory = BrokerProxyClientFactory(_FakeProxyClient(), endpoint="atlas-replica")
        factory.close()
