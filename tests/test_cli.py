"""Tests for the CLI argument parsing."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from ami_mcp.cli import main


class TestCLIServe:
    def test_serve_calls_serve(self) -> None:
        captured: dict[str, Any] = {}

        def fake_serve(**kwargs: Any) -> None:
            captured["called"] = True
            captured["kwargs"] = kwargs

        with (
            patch("sys.argv", ["ami-mcp", "serve"]),
            patch("ami_mcp.cli.serve", fake_serve),
        ):
            main()

        assert captured.get("called") is True
        assert captured["kwargs"]["transport"] == "stdio"
        assert captured["kwargs"]["host"] == "127.0.0.1"
        assert captured["kwargs"]["port"] == 8000

    def test_serve_http_flags_are_forwarded(self) -> None:
        captured: dict[str, Any] = {}

        def fake_serve(**kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        argv = [
            "ami-mcp",
            "serve",
            "--transport",
            "http",
            "--host",
            "0.0.0.0",
            "--port",
            "8123",
            "--shared-secret",
            "s3cr3t",
            "--resource-url",
            "https://ami.example.org",
        ]
        with (
            patch("sys.argv", argv),
            patch("ami_mcp.cli.serve", fake_serve),
        ):
            main()

        assert captured["kwargs"] == {
            "transport": "http",
            "host": "0.0.0.0",
            "port": 8123,
            "auth": "shared-secret",
            "shared_secret": "s3cr3t",
            "resource_url": "https://ami.example.org",
            "broker_url": None,
            "broker_jwks_url": None,
            "broker_issuer": None,
            "audience": "ami",
            "forwarded_allow_ips": "127.0.0.1",
            "log_level": "info",
        }

    def test_serve_broker_flags_are_forwarded(self) -> None:
        captured: dict[str, Any] = {}

        def fake_serve(**kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        argv = [
            "ami-mcp",
            "serve",
            "--transport",
            "http",
            "--auth",
            "broker",
            "--broker-url",
            "https://mcp.af.uchicago.edu",
        ]
        with (
            patch("sys.argv", argv),
            patch("ami_mcp.cli.serve", fake_serve),
        ):
            main()

        assert captured["kwargs"]["auth"] == "broker"
        assert captured["kwargs"]["broker_url"] == "https://mcp.af.uchicago.edu"
        assert captured["kwargs"]["audience"] == "ami"

    def test_no_command_does_not_call_serve(self) -> None:
        captured: dict[str, bool] = {}

        def fake_serve() -> None:
            captured["called"] = True

        with (
            patch("sys.argv", ["ami-mcp"]),
            patch("ami_mcp.cli.serve", fake_serve),
        ):
            main()

        assert "called" not in captured
