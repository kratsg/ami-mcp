"""Tests for server startup preflight checks."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from ami_mcp.server import _configure_logging, _preflight_check


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
