"""Broker mode: per-user AMI access behind the AF MCP credential broker.

In broker mode this server sits behind af-mcp-platform's aggregator, which
forwards a broker-issued identity JWT (RS256, ``aud`` = this backend) as the
request bearer. The token is verified against the broker's JWKS, and the same
bearer is then redeemed at the broker for the caller's VOMS proxy, which
backs a pyAMI client for exactly one AMI call — the proxy file is deleted the
moment the call finishes (never persisted; af-mcp-platform issue #112).

Requires the ``broker`` extra: ``pip install ami-mcp[broker]``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pyAMI.client

from ami_mcp.auth.factory import AmiClientFactory

try:
    from af_credentials.mcp import mcp_token_verifier
    from af_credentials.proxy import ProxyClient
    from af_credentials.verifier import BrokerTokenVerifier

    HAS_AF_CREDENTIALS = True
except ImportError:  # pragma: no cover - exercised only without the extra
    HAS_AF_CREDENTIALS = False

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.auth.provider import TokenVerifier

MISSING_AF_CREDENTIALS_MSG = (
    "broker mode requires the af-credentials package. "
    "Install it via the 'broker' extra: pip install ami-mcp[broker]"
)


def extract_bearer(ctx: Any) -> str:
    """Return the bearer token from the current request's Authorization header.

    The token has already been verified by the server's TokenVerifier before
    any tool runs; this re-reads it so it can be redeemed at the broker.

    Raises:
        PermissionError: If the header is missing or not a Bearer scheme.
    """
    auth = ctx.request_context.request.headers.get("authorization", "") or ""
    if not auth.lower().startswith("bearer "):
        msg = "Missing Bearer token in Authorization header"
        raise PermissionError(msg)
    return auth[7:].strip()


def make_broker_token_verifier(
    jwks_url: str, issuer: str, audience: str
) -> TokenVerifier:
    """Build the mcp TokenVerifier that checks broker-issued identity JWTs."""
    if not HAS_AF_CREDENTIALS:
        raise ImportError(MISSING_AF_CREDENTIALS_MSG)
    verifier: TokenVerifier = mcp_token_verifier(
        BrokerTokenVerifier(jwks_url, issuer, audience)
    )
    return verifier


def make_proxy_client(broker_url: str) -> Any:
    """Build the af-credentials ProxyClient used to redeem VOMS proxies."""
    if not HAS_AF_CREDENTIALS:
        raise ImportError(MISSING_AF_CREDENTIALS_MSG)
    return ProxyClient(broker_url)


class BrokerProxyClientFactory(AmiClientFactory):
    """Back each AMI call with the caller's freshly redeemed VOMS proxy.

    Every call redeems the request bearer at the broker (the broker caches
    the proxy; redeeming is a cheap in-cluster round trip), materializes the
    PEM as a private 0600 file, points a fresh pyAMI client at it via
    ``key_file``/``cert_file``, and deletes the file as soon as the call
    completes — success or failure. Nothing is cached server-side.
    """

    def __init__(self, proxy_client: Any, *, endpoint: str) -> None:
        """Store the redeem client and the pyAMI endpoint to target."""
        self._proxy_client = proxy_client
        self._endpoint = endpoint

    @asynccontextmanager
    async def _scoped(self, ctx: Any) -> AsyncIterator[Any]:
        bearer = extract_bearer(ctx)
        with await self._proxy_client.proxy_file(bearer) as handle:
            yield pyAMI.client.Client(
                self._endpoint,
                key_file=str(handle.path),
                cert_file=str(handle.path),
            )

    def get_client(self, ctx: Any) -> Any:
        """Return a context manager over a proxy-backed per-call client."""
        return self._scoped(ctx)

    def close(self) -> None:
        """Nothing to release: proxy files are deleted per call."""
