"""MCP server setup for ami-mcp."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyAMI.client
import pyAMI_atlas.api as _atlas_api  # noqa: F401 (side-effect: registers ATLAS endpoints)
import uvicorn
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse

from ami_mcp.auth.broker import (
    BrokerProxyClientFactory,
    make_broker_token_verifier,
    make_proxy_client,
)
from ami_mcp.auth.factory import EnvBasedClientFactory
from ami_mcp.auth.shared_secret import SharedSecretVerifier
from ami_mcp.nomenclature import AMI_QUERY_LANGUAGE, ATLAS_NOMENCLATURE
from ami_mcp.resources import register as register_resources
from ami_mcp.tools import datasets, execute, hashtags, physics, tags, validate, xsecdb

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from starlette.applications import Starlette
    from starlette.requests import Request

_INSTRUCTIONS = (
    "MCP server for the ATLAS AMI metadata interface and PMG Central Page. "
    "Provides tools to search for MC samples by hashtag classification, "
    "retrieve dataset metadata (cross-sections, filter efficiencies, k-factors), "
    "execute arbitrary AMI queries, and look up cross-section database entries. "
    "Read the ami://query-language resource to learn how to construct AMI queries "
    "for use with ami_execute. Authentication requires a valid VOMS proxy "
    "(X509_USER_PROXY env var or /tmp/x509up_u<uid>).\n\n"
    + ATLAS_NOMENCLATURE
    + "\n\n"
    + AMI_QUERY_LANGUAGE
)


def _preflight_check() -> None:
    """Check environment before starting the MCP server.

    Prints clear diagnostics to stderr and exits non-zero if required
    configuration is missing.
    """
    warnings: list[str] = []

    # --- VOMS proxy ---
    proxy_path = os.environ.get("X509_USER_PROXY")
    if proxy_path:
        if not Path(proxy_path).exists():
            warnings.append(
                f"X509_USER_PROXY={proxy_path!r} is set but the file does not exist.\n"
                "    Run: voms-proxy-init -voms atlas"
            )
    else:
        uid = os.getuid() if hasattr(os, "getuid") else 0
        default_proxy = Path(f"/tmp/x509up_u{uid}")
        if not default_proxy.exists():
            warnings.append(
                "No VOMS proxy found. AMI requires a valid grid proxy.\n"
                "    Run: voms-proxy-init -voms atlas\n"
                "    Or set: export X509_USER_PROXY=/path/to/proxy"
            )

    # --- X509_CERT_DIR ---
    cert_dir = os.environ.get("X509_CERT_DIR")
    if cert_dir is None:
        warnings.append(
            "X509_CERT_DIR is not set. SSL certificate verification may fail.\n"
            "    Example:\n"
            "      export X509_CERT_DIR=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase"
            "/etc/grid-security-emi/certificates"
        )
    elif not Path(cert_dir).is_dir():
        warnings.append(
            f"X509_CERT_DIR={cert_dir!r} does not exist or is not a directory.\n"
            "    SSL certificate verification may fail."
        )

    for w in warnings:
        sys.stderr.write(f"[ami-mcp] WARNING: {w}\n")


def _configure_logging(log_level: str) -> None:
    """Apply the CLI log level to the root logger.

    ``uvicorn.run(log_level=...)`` configures only uvicorn's own loggers, so
    library loggers (e.g. af_credentials.verifier's DEBUG token-rejection
    reasons, mcp SDK internals) would otherwise never reach a handler.
    basicConfig attaches a stderr handler only if none exists; the level is
    set explicitly so it applies even when a handler is already configured.
    """
    logging.basicConfig(
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger().setLevel(log_level.upper())


def _register_all(mcp: MCPServer) -> None:
    """Register every tool module and the MCP resources on *mcp*."""
    for _module in [execute, datasets, hashtags, physics, tags, xsecdb, validate]:
        _module.register(mcp)
    register_resources(mcp)


def _make_mcp() -> MCPServer:
    """Build and return a configured MCPServer instance for stdio."""

    @asynccontextmanager
    async def _lifespan(_server: MCPServer) -> AsyncGenerator[dict[str, Any], None]:
        """Initialize the pyAMI client for the lifetime of the MCP server.

        The client reads the VOMS proxy from X509_USER_PROXY or the default
        /tmp/x509up_u<uid> path. Set X509_CERT_DIR for SSL cert verification.
        """
        endpoint = os.environ.get("AMI_ENDPOINT", "atlas-replica")
        factory = EnvBasedClientFactory(client=pyAMI.client.Client(endpoint))
        try:
            yield {"client_factory": factory}
        finally:
            factory.close()

    mcp = MCPServer("ami-mcp", lifespan=_lifespan, instructions=_INSTRUCTIONS)
    _register_all(mcp)
    return mcp


def _make_shared_secret_app(
    *,
    secret: str,
    resource_url: str,
    host: str,
) -> Starlette:
    """Build the ASGI app for HTTP transport gated by a static bearer.

    Serves one env-configured pyAMI identity (exactly like stdio, e.g. a
    server-managed VOMS proxy) behind a server-wide shared secret enforced by
    ``SharedSecretVerifier``. Clients are handed out per request because
    pyAMI's HttpClient is not safe under concurrent use.

    The returned Starlette app is used as the uvicorn root app; in mcp v2 it
    carries the session-manager lifespan itself, so no extra wiring is needed.
    """

    @asynccontextmanager
    async def _lifespan(_server: MCPServer) -> AsyncGenerator[dict[str, Any], None]:
        endpoint = os.environ.get("AMI_ENDPOINT", "atlas-replica")
        factory = EnvBasedClientFactory(endpoint=endpoint)
        try:
            yield {"client_factory": factory}
        finally:
            factory.close()

    mcp = MCPServer(
        "ami-mcp",
        instructions=_INSTRUCTIONS,
        lifespan=_lifespan,
        token_verifier=SharedSecretVerifier(secret),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(resource_url),
            # No OAuth authorization server backs this resource; clients
            # present the static bearer out-of-band, so do not advertise a
            # (non-existent) protected-resource discovery chain.
            resource_server_url=None,
            client_registration_options=ClientRegistrationOptions(enabled=False),
            required_scopes=[],
        ),
    )
    _register_all(mcp)

    async def _healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Call form instead of decorator: custom_route lacks a return annotation
    # in the SDK, and an untyped decorator strips _healthz's type under mypy.
    mcp.custom_route("/healthz", methods=["GET"])(_healthz)

    return mcp.streamable_http_app(streamable_http_path="/mcp", host=host)


def _make_broker_app(
    *,
    broker_url: str,
    jwks_url: str,
    issuer: str,
    audience: str,
    resource_url: str,
    host: str,
) -> Starlette:
    """Build the ASGI app for HTTP transport behind the AF credential broker.

    Bearers are broker-issued identity JWTs verified against the broker's
    JWKS; each AMI call redeems the caller's VOMS proxy at the broker and
    disposes of it immediately afterwards (see ``ami_mcp.auth.broker``).
    """
    verifier = make_broker_token_verifier(jwks_url, issuer, audience)
    proxy_client = make_proxy_client(broker_url)

    @asynccontextmanager
    async def _lifespan(_server: MCPServer) -> AsyncGenerator[dict[str, Any], None]:
        endpoint = os.environ.get("AMI_ENDPOINT", "atlas-replica")
        factory = BrokerProxyClientFactory(proxy_client, endpoint=endpoint)
        try:
            yield {"client_factory": factory}
        finally:
            factory.close()

    mcp = MCPServer(
        "ami-mcp",
        instructions=_INSTRUCTIONS,
        lifespan=_lifespan,
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(resource_url),
            # The aggregator injects the bearer itself; there is no OAuth
            # discovery chain to advertise on this resource.
            resource_server_url=None,
            client_registration_options=ClientRegistrationOptions(enabled=False),
            required_scopes=[],
        ),
    )
    _register_all(mcp)

    async def _healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    mcp.custom_route("/healthz", methods=["GET"])(_healthz)

    return mcp.streamable_http_app(streamable_http_path="/mcp", host=host)


def serve(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    auth: str = "shared-secret",
    shared_secret: str | None = None,
    resource_url: str | None = None,
    broker_url: str | None = None,
    broker_jwks_url: str | None = None,
    broker_issuer: str | None = None,
    audience: str = "ami",
    forwarded_allow_ips: str = "127.0.0.1",
    log_level: str = "info",
) -> None:
    """Start the MCP server over the selected transport."""
    if shared_secret and transport == "stdio":
        sys.stderr.write(
            "[ami-mcp] Error: --shared-secret requires --transport http "
            "(it is ignored by stdio transport).\n"
        )
        sys.exit(1)

    if transport == "stdio":
        _preflight_check()
        _make_mcp().run(transport="stdio")
        return

    if auth == "broker":
        if shared_secret:
            sys.stderr.write(
                "[ami-mcp] Error: --shared-secret conflicts with --auth broker; "
                "pick one HTTP auth mode.\n"
            )
            sys.exit(1)
        if not broker_url:
            sys.stderr.write(
                "[ami-mcp] Error: --auth broker requires --broker-url "
                "(or AMI_MCP_BROKER_URL).\n"
            )
            sys.exit(1)
        # No env-proxy preflight: per-user proxies arrive at runtime via the
        # broker; the server itself holds no AMI credential.
        app = _make_broker_app(
            broker_url=broker_url,
            jwks_url=broker_jwks_url
            or f"{broker_url.rstrip('/')}/.well-known/jwks.json",
            issuer=broker_issuer or broker_url,
            audience=audience,
            resource_url=resource_url or f"http://{host}:{port}",
            host=host,
        )
    else:
        # HTTP transport, shared-secret mode.
        if not shared_secret:
            sys.stderr.write(
                "[ami-mcp] Error: HTTP transport requires --shared-secret "
                "(or AMI_MCP_SHARED_SECRET), or --auth broker.\n"
            )
            sys.exit(1)

        sys.stderr.write(
            "[ami-mcp] NOTICE: shared-secret HTTP mode is active — all access is "
            "gated by a single static bearer and every request shares the "
            "server's env-configured AMI identity.\n"
        )
        _preflight_check()
        app = _make_shared_secret_app(
            secret=shared_secret,
            resource_url=resource_url or f"http://{host}:{port}",
            host=host,
        )

    # HTTP transport only: stdio uses stdout for the MCP protocol and gets no
    # root logging configuration, matching where log_level is honored today.
    _configure_logging(log_level)
    uvicorn.run(
        app,
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
        log_level=log_level,
    )
