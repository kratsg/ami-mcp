"""Tests for the shared-secret HTTP transport."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from ami_mcp.server import _make_shared_secret_app, serve

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = _make_shared_secret_app(
        secret="s3cr3t",
        resource_url="http://testserver",
        host="127.0.0.1",
    )
    # Enter the context manager so the app lifespan (and with it the mcp
    # session manager) actually runs. base_url must agree with host= above:
    # binding to a localhost address enables the SDK's DNS-rebinding Host
    # allow-listing, whose patterns ("127.0.0.1:*") require an explicit port
    # and reject the TestClient default "testserver".
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


class TestHealthzEndpoint:
    def test_healthz_needs_no_auth(self, client: TestClient) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestUnauthenticatedAccess:
    def test_mcp_without_bearer_is_401(self, client: TestClient) -> None:
        response = client.post("/mcp", json=_INITIALIZE, headers=_MCP_HEADERS)
        assert response.status_code == 401

    def test_mcp_with_wrong_bearer_is_401(self, client: TestClient) -> None:
        response = client.post(
            "/mcp",
            json=_INITIALIZE,
            headers={**_MCP_HEADERS, "Authorization": "Bearer wrong"},
        )
        assert response.status_code == 401


class TestSharedSecretMode:
    def test_initialize_with_correct_bearer(self, client: TestClient) -> None:
        response = client.post(
            "/mcp",
            json=_INITIALIZE,
            headers={**_MCP_HEADERS, "Authorization": "Bearer s3cr3t"},
        )
        assert response.status_code == 200
        assert "serverInfo" in response.text


class TestServeGuards:
    def test_shared_secret_with_stdio_exits(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            serve(transport="stdio", shared_secret="s3cr3t")
        assert excinfo.value.code == 1

    def test_http_without_shared_secret_exits(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            serve(transport="http")
        assert excinfo.value.code == 1
