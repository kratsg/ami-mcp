"""Factories that provide a pyAMI client for the current request.

Tools never construct or hold a pyAMI client directly; they call
``get_ami_client(ctx)`` (see ``ami_mcp.tools._helpers``), which delegates to
the factory stored in the lifespan context. The factory decides whether that
means one process-wide client (stdio) or a per-request client (HTTP modes,
where per-user credentials or concurrency demand it).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pyAMI.client


class AmiClientFactory(ABC):
    """Contract for obtaining a pyAMI client for the current request."""

    @abstractmethod
    def get_client(self, ctx: Any) -> Any:
        """Return a pyAMI client appropriate for the request in *ctx*."""

    def close(self) -> None:
        """Release any resources held by the factory."""


class EnvBasedClientFactory(AmiClientFactory):
    """Serve a pyAMI client configured from the environment (VOMS proxy).

    Two modes, selected at construction:

    - ``client=...``: always return that single shared instance. Used for
      stdio, where requests are serial.
    - ``endpoint=...``: build a fresh ``pyAMI.client.Client`` on every call.
      Used for HTTP modes — pyAMI's HttpClient keeps connection state on
      ``self``, so a shared instance is not safe under concurrent requests.
      Construction only touches the filesystem (proxy/config discovery), so
      per-call construction is cheap.
    """

    def __init__(self, client: Any = None, *, endpoint: str | None = None) -> None:
        if (client is None) == (endpoint is None):
            msg = "provide exactly one of client= or endpoint="
            raise ValueError(msg)
        self._client = client
        self._endpoint = endpoint

    def get_client(self, ctx: Any) -> Any:  # noqa: ARG002
        """Return the shared client, or a fresh one in endpoint mode."""
        if self._client is not None:
            return self._client
        return pyAMI.client.Client(self._endpoint)
