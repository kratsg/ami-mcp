"""Factories that provide a pyAMI client for the current request.

Tools never construct or hold a pyAMI client directly; they call
``run_ami_command(ctx, ...)`` (see ``ami_mcp.tools._helpers``), which asks
the factory stored in the lifespan context for a client scoped to that one
call. The factory decides what that means: one process-wide client (stdio),
a per-request client (HTTP modes, where concurrency demands it), or a
per-call client backed by a redeemed user credential that must be disposed
of as soon as the call finishes (broker mode).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pyAMI.client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class AmiClientFactory(ABC):
    """Contract for obtaining a pyAMI client scoped to the current request."""

    @abstractmethod
    def get_client(self, ctx: Any) -> Any:
        """Return an async context manager yielding a pyAMI client.

        The client (and any credential backing it) is only guaranteed valid
        inside the ``async with`` block.
        """

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the factory."""


class EnvBasedClientFactory(AmiClientFactory):
    """Serve a pyAMI client configured from the environment (VOMS proxy).

    Two modes, selected at construction:

    - ``client=...``: always yield that single shared instance. Used for
      stdio, where requests are serial.
    - ``endpoint=...``: build a fresh ``pyAMI.client.Client`` on every call.
      Used for HTTP modes — pyAMI's HttpClient keeps connection state on
      ``self``, so a shared instance is not safe under concurrent requests.
      Construction only touches the filesystem (proxy/config discovery), so
      per-call construction is cheap.
    """

    def __init__(self, client: Any = None, *, endpoint: str | None = None) -> None:
        """Select client= for a shared instance or endpoint= for per-call construction."""
        if (client is None) == (endpoint is None):
            msg = "provide exactly one of client= or endpoint="
            raise ValueError(msg)
        self._client = client
        self._endpoint = endpoint

    @asynccontextmanager
    async def _scoped(self) -> AsyncIterator[Any]:
        if self._client is not None:
            yield self._client
        else:
            yield pyAMI.client.Client(self._endpoint)

    def get_client(self, ctx: Any) -> Any:  # noqa: ARG002
        """Return a context manager over the shared or per-call client."""
        return self._scoped()

    def close(self) -> None:
        """Nothing to release: pyAMI clients hold no persistent connections."""
