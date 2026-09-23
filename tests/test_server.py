"""Tests for server startup preflight checks."""

from __future__ import annotations

import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from ami_mcp.auth.factory import EnvBasedClientFactory
from ami_mcp.policy import DEFAULT_ALLOWED_COMMANDS
from ami_mcp.server import _configure_logging, _preflight_check, _register_all

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_JSON_RPC_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _initialize_session(client: TestClient) -> dict[str, str]:
    """Do the MCP initialize handshake over *client* and return headers carrying the session id."""
    init_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers=_JSON_RPC_HEADERS,
    )
    session_id = init_resp.headers["mcp-session-id"]
    headers = {**_JSON_RPC_HEADERS, "mcp-session-id": session_id}
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=headers,
    )
    return headers


class TestConfigureLogging:
    @pytest.fixture(autouse=True)
    def _restore_root_level(self):
        """Restore the root logger level so tests don't leak configuration."""
        root = logging.getLogger()
        original = root.level
        yield
        root.setLevel(original)

    def test_debug_enables_library_debug_logging(self) -> None:
        """--log-level debug must reach library loggers, not just uvicorn's."""
        _configure_logging("debug")
        assert logging.getLogger("af_credentials.verifier").isEnabledFor(logging.DEBUG)

    def test_info_does_not_enable_debug(self) -> None:
        _configure_logging("info")
        verifier = logging.getLogger("af_credentials.verifier")
        assert not verifier.isEnabledFor(logging.DEBUG)
        assert verifier.isEnabledFor(logging.INFO)

    def test_warning_silences_info(self) -> None:
        _configure_logging("warning")
        verifier = logging.getLogger("af_credentials.verifier")
        assert not verifier.isEnabledFor(logging.INFO)
        assert verifier.isEnabledFor(logging.WARNING)


class TestPreflightCheck:
    def test_warns_when_no_proxy_and_no_default(self, capsys) -> None:
        """Warn when no proxy is configured and default path doesn't exist."""
        with patch.dict("os.environ", {}, clear=True):
            _preflight_check()
        err = capsys.readouterr().err
        assert "proxy" in err.lower() or "X509" in err

    def test_warns_when_proxy_file_missing(self, capsys, tmp_path) -> None:
        env = {"X509_USER_PROXY": str(tmp_path / "nonexistent.pem")}
        with patch.dict("os.environ", env, clear=True):
            _preflight_check()
        assert "X509_USER_PROXY" in capsys.readouterr().err

    def test_no_proxy_warning_when_proxy_exists(self, capsys, tmp_path) -> None:
        proxy = tmp_path / "proxy.pem"
        proxy.touch()
        env = {
            "X509_USER_PROXY": str(proxy),
            "X509_CERT_DIR": str(tmp_path),
        }
        with patch.dict("os.environ", env, clear=True):
            _preflight_check()
        assert "X509_USER_PROXY" not in capsys.readouterr().err

    def test_warns_when_cert_dir_not_set(self, capsys, tmp_path) -> None:
        proxy = tmp_path / "proxy.pem"
        proxy.touch()
        env = {"X509_USER_PROXY": str(proxy)}
        with patch.dict("os.environ", env, clear=True):
            _preflight_check()
        assert "X509_CERT_DIR" in capsys.readouterr().err

    def test_warns_when_cert_dir_nonexistent(self, capsys, tmp_path) -> None:
        proxy = tmp_path / "proxy.pem"
        proxy.touch()
        env = {
            "X509_USER_PROXY": str(proxy),
            "X509_CERT_DIR": str(tmp_path / "nonexistent"),
        }
        with patch.dict("os.environ", env, clear=True):
            _preflight_check()
        assert "X509_CERT_DIR" in capsys.readouterr().err

    def test_no_warnings_with_valid_config(self, capsys, tmp_path) -> None:
        proxy = tmp_path / "proxy.pem"
        proxy.touch()
        env = {
            "X509_USER_PROXY": str(proxy),
            "X509_CERT_DIR": str(tmp_path),
        }
        with patch.dict("os.environ", env, clear=True):
            _preflight_check()
        assert capsys.readouterr().err == ""


class TestToolRegistrationDrift:
    def test_every_tool_declares_annotations_and_output_schema(self) -> None:
        """Drift guard: every ami_* tool must publish read-only annotations and an outputSchema.

        This is the one test that would catch a future tool being added (or
        an existing one being refactored) without following the
        Annotated[CallToolResult, Model] + ToolAnnotations pattern all 12
        tools use today -- see CLAUDE.md's "Tool registration pattern" section.
        """
        mcp = MCPServer("test")
        _register_all(mcp)
        tools = list(mcp._tool_manager.list_tools())
        assert len(tools) == 12
        for tool in tools:
            assert tool.annotations is not None, tool.name
            assert tool.annotations.read_only_hint is not None, tool.name
            assert tool.output_schema is not None, tool.name


class TestStdioAppOverTheWire:
    """Wire-level assertions that bypass every unit test's tool.fn shortcut.

    Every existing tool test calls the raw callable directly, which never
    goes through the mcp SDK's serialization -- none of them would notice a
    missing `annotations`/`outputSchema` on the wire. These do, via a real
    JSON-RPC round trip through the built ASGI app.
    """

    @pytest.fixture
    def mock_ami_client(self) -> MagicMock:
        client = MagicMock()
        result_mock = MagicMock()
        result_mock.get_rows.return_value = [
            OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])
        ]
        client.execute.return_value = result_mock
        return client

    @pytest.fixture
    def app(self, mock_ami_client: MagicMock) -> Any:
        @asynccontextmanager
        async def _lifespan(_server: MCPServer) -> AsyncGenerator[dict[str, Any], None]:
            yield {
                "client_factory": EnvBasedClientFactory(client=mock_ami_client),
                "allowed_commands": DEFAULT_ALLOWED_COMMANDS,
            }

        mcp = MCPServer("test", lifespan=_lifespan)
        _register_all(mcp)
        return mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True)

    @pytest.fixture
    def client(self, app: Any):
        with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
            yield test_client

    def test_tools_list_carries_annotations_and_output_schema(
        self, client: TestClient
    ) -> None:
        headers = _initialize_session(client)
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=headers,
        )
        assert resp.status_code == 200
        tools = {tool["name"]: tool for tool in resp.json()["result"]["tools"]}
        assert "ami_execute" in tools
        for tool in tools.values():
            assert tool["annotations"]["readOnlyHint"] is True
            assert tool["outputSchema"] is not None

    def test_tools_call_carries_text_and_structured_content(
        self, client: TestClient
    ) -> None:
        headers = _initialize_session(client)
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "ami_execute",
                    "arguments": {
                        "command": (
                            "SearchQuery -catalog=mc23_001:production -entity=HASHTAGS"
                        )
                    },
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        assert result["content"][0]["type"] == "text"
        assert "WeakBoson" in result["content"][0]["text"]
        structured = result["structuredContent"]
        assert structured["command"] == (
            "SearchQuery -catalog=mc23_001:production -entity=HASHTAGS"
        )
        assert structured["total"] == 1

    def test_tools_call_error_sets_is_error(
        self, client: TestClient, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("ATLAS_PMGXSEC_PATH", str(tmp_path / "nonexistent"))
        headers = _initialize_session(client)
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "ami_list_xsec_databases",
                    "arguments": {},
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "structuredContent" not in result or result["structuredContent"] is None

    def test_tools_call_rejects_a_non_allowlisted_command_verb(
        self, client: TestClient
    ) -> None:
        """The only end-to-end proof a rejection serializes correctly through convert_result."""
        headers = _initialize_session(client)
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "ami_execute",
                    "arguments": {"command": "GetElementInfo -x=1"},
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "structuredContent" not in result or result["structuredContent"] is None
        assert "GetElementInfo" in result["content"][0]["text"]
