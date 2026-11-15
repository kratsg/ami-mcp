"""End-to-end observability tests over HTTP, against the real app and a real JWKS endpoint."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from ami_mcp.policy import DEFAULT_ALLOWED_COMMANDS
from ami_mcp.server import _make_broker_app, _make_shared_secret_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from conftest import JsonLog

AUDIENCE = "ami"
KID = "test-kid"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def _tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


class JwksServer:
    """A local HTTP server publishing one RSA key as a JWKS and counting fetches."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self._body = json.dumps(
            {"keys": [{**jwk, "kid": KID, "alg": "RS256"}]}
        ).encode()
        self.fetches = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.fetches += 1
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(outer._body)

            def log_message(self, *_args: object) -> None:
                """Keep the test output pristine."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        """Begin serving in a background thread."""
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and release the port."""
        self._server.shutdown()
        self._server.server_close()

    def token(self, sub: str = "user-sub-1") -> str:
        """Sign a broker identity token for this server's issuer and the ami audience."""
        now = int(time.time())
        claims = {
            "iss": self.url,
            "sub": sub,
            "aud": AUDIENCE,
            "jti": "jti-1",
            "iat": now,
            "exp": now + 600,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": KID})


def _call_tool(
    client: TestClient,
    bearer: str,
    request_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> None:
    """Run initialize and one tool call, the second carrying the X-Request-ID."""
    base = {**HEADERS, "Authorization": f"Bearer {bearer}"}
    init = client.post("/mcp", json=INITIALIZE, headers=base)
    assert init.status_code == 200
    session = init.headers.get("mcp-session-id")
    if session:
        base["mcp-session-id"] = session
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=base,
    )
    response = client.post(
        "/mcp",
        json=_tool_call(tool, arguments),
        headers={**base, "X-Request-ID": request_id},
    )
    assert response.status_code == 200


@pytest.fixture
def xsec_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real, empty PMG cross-section directory so tools run without AMI."""
    monkeypatch.setenv("ATLAS_PMGXSEC_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def jwks() -> Iterator[JwksServer]:
    server = JwksServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def broker_client(jwks: JwksServer) -> Iterator[TestClient]:
    app = _make_broker_app(
        broker_url=jwks.url,
        jwks_url=f"{jwks.url}/.well-known/jwks.json",
        issuer=jwks.url,
        audience=AUDIENCE,
        resource_url="http://127.0.0.1:8000",
        host="127.0.0.1",
        allowed_commands=DEFAULT_ALLOWED_COMMANDS,
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield client


@pytest.fixture
def shared_secret_client() -> Iterator[TestClient]:
    app = _make_shared_secret_app(
        secret="s3cr3t",
        resource_url="http://127.0.0.1:8000",
        host="127.0.0.1",
        allowed_commands=DEFAULT_ALLOWED_COMMANDS,
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield client


@pytest.mark.usefixtures("xsec_dir")
class TestBrokerModeLogging:
    def test_every_line_of_a_request_carries_its_request_id(
        self, broker_client: TestClient, jwks: JwksServer, json_log: JsonLog
    ) -> None:
        _call_tool(broker_client, jwks.token(), "abc", "ami_list_xsec_databases", {})

        lines = [line for line in json_log.lines() if line.get("request_id") == "abc"]
        assert {"tool.call", "http.request"} <= {line["event"] for line in lines}
        # Only the initialize/notification requests may carry another id.
        assert all(
            line["request_id"] == "abc"
            for line in json_log.lines()
            if line["event"] == "tool.call"
        )

    def test_tool_call_line_has_the_standard_fields(
        self, broker_client: TestClient, jwks: JwksServer, json_log: JsonLog
    ) -> None:
        _call_tool(
            broker_client, jwks.token("kratsg"), "abc", "ami_list_xsec_databases", {}
        )

        (call,) = [line for line in json_log.lines() if line["event"] == "tool.call"]
        assert call["tool"] == "ami_list_xsec_databases"
        assert call["subject"] == "kratsg"
        assert call["outcome"] == "ok"
        assert call["duration_ms"] >= 0
        assert call["level"] == "info"
        assert call["logger"]
        assert call["timestamp"]

    def test_tool_error_result_is_an_error_outcome(
        self,
        broker_client: TestClient,
        jwks: JwksServer,
        json_log: JsonLog,
        xsec_dir: Path,
    ) -> None:
        xsec_dir.rmdir()

        _call_tool(broker_client, jwks.token(), "abc", "ami_list_xsec_databases", {})

        (call,) = [line for line in json_log.lines() if line["event"] == "tool.call"]
        assert call["outcome"] == "error"

    def test_no_line_contains_the_token_or_arguments(
        self, broker_client: TestClient, jwks: JwksServer, json_log: JsonLog
    ) -> None:
        token = jwks.token()

        _call_tool(broker_client, token, "abc", "ami_lookup_xsec", {"dsid": 424242})

        written = json_log.stream.getvalue()
        assert token not in written
        assert "424242" not in written

    def test_successful_probe_writes_no_line(
        self, broker_client: TestClient, json_log: JsonLog
    ) -> None:
        for _ in range(3):
            assert broker_client.get("/healthz").status_code == 200

        assert json_log.lines() == []

    def test_mcp_request_keeps_its_access_line(
        self, broker_client: TestClient, json_log: JsonLog
    ) -> None:
        broker_client.post("/mcp", json=INITIALIZE, headers=HEADERS)

        access = [line for line in json_log.lines() if line["event"] == "http.request"]
        assert [(line["path"], line["status"]) for line in access] == [("/mcp", 401)]

    def test_repeated_requests_fetch_the_jwks_once(
        self, broker_client: TestClient, jwks: JwksServer
    ) -> None:
        token = jwks.token()

        for index in range(5):
            _call_tool(
                broker_client, token, f"req-{index}", "ami_list_xsec_databases", {}
            )

        assert jwks.fetches == 1


@pytest.mark.usefixtures("xsec_dir")
class TestSharedSecretModeLogging:
    def test_tool_call_carries_request_id_and_no_subject(
        self, shared_secret_client: TestClient, json_log: JsonLog
    ) -> None:
        _call_tool(shared_secret_client, "s3cr3t", "abc", "ami_list_xsec_databases", {})

        (call,) = [line for line in json_log.lines() if line["event"] == "tool.call"]
        assert call["request_id"] == "abc"
        assert call["outcome"] == "ok"
        assert "subject" not in call
