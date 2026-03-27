"""Tests for the CLI argument parsing."""

from __future__ import annotations

from unittest.mock import patch

from ami_mcp.cli import main


class TestCLIServe:
    def test_serve_calls_serve(self) -> None:
        captured: dict[str, bool] = {}

        def fake_serve() -> None:
            captured["called"] = True

        with (
            patch("sys.argv", ["ami-mcp", "serve"]),
            patch("ami_mcp.cli.serve", fake_serve),
        ):
            main()

        assert captured.get("called") is True

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
