"""Guard for the pytest warning filter covering pyAMI's TLS context setup."""

from __future__ import annotations

import warnings

import pyAMI.httpclient
import pytest


def test_pyami_tls_context_does_not_error_under_the_warning_filters() -> None:
    # pyAMI builds ssl.SSLContext(ssl.PROTOCOL_TLS), a DeprecationWarning on
    # Python 3.12+; the project's `error` filter would turn every live AMI call
    # into an exception without the scoped ignore in pyproject.toml.
    client = pyAMI.httpclient.HttpClient(config=None)
    client.create_context()


def test_other_deprecation_warnings_still_error() -> None:
    # The pyAMI ignore must stay narrow: an unrelated DeprecationWarning from
    # another module is still an error.
    with pytest.raises(DeprecationWarning):
        warnings.warn("something else is deprecated", DeprecationWarning, stacklevel=1)
