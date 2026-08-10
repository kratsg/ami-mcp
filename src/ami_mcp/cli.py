"""Command-line interface for ami-mcp."""

from __future__ import annotations

import argparse
import os

from ami_mcp.server import serve


def main() -> None:
    """Entry point for the ami-mcp command."""
    parser = argparse.ArgumentParser(
        prog="ami-mcp",
        description="MCP Server for ATLAS AMI metadata interface",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the MCP server",
    )
    serve_parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="Transport to serve on (default: stdio)",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address for HTTP transport (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)",
    )
    serve_parser.add_argument(
        "--shared-secret",
        default=os.environ.get("AMI_MCP_SHARED_SECRET"),
        help=(
            "Static bearer secret gating HTTP access to the server's "
            "env-configured AMI identity (env: AMI_MCP_SHARED_SECRET). "
            "Prefer the env var so the secret stays out of process listings."
        ),
    )
    serve_parser.add_argument(
        "--resource-url",
        default=os.environ.get("AMI_MCP_RESOURCE_URL"),
        help=(
            "Externally visible base URL of this server "
            "(env: AMI_MCP_RESOURCE_URL; default: http://HOST:PORT)"
        ),
    )
    serve_parser.add_argument(
        "--auth",
        choices=("shared-secret", "broker"),
        default="shared-secret",
        help=(
            "HTTP auth mode: 'shared-secret' gates the server's own AMI "
            "identity behind a static bearer; 'broker' verifies AF-broker-"
            "issued JWTs and redeems per-user VOMS proxies (default: "
            "shared-secret)"
        ),
    )
    serve_parser.add_argument(
        "--broker-url",
        default=os.environ.get("AMI_MCP_BROKER_URL"),
        help="AF credential broker base URL for --auth broker (env: AMI_MCP_BROKER_URL)",
    )
    serve_parser.add_argument(
        "--broker-jwks-url",
        default=os.environ.get("AMI_MCP_BROKER_JWKS_URL"),
        help=(
            "JWKS URL for verifying broker-issued JWTs "
            "(env: AMI_MCP_BROKER_JWKS_URL; default: BROKER_URL/.well-known/jwks.json)"
        ),
    )
    serve_parser.add_argument(
        "--broker-issuer",
        default=os.environ.get("AMI_MCP_BROKER_ISSUER"),
        help="Expected iss claim of broker-issued JWTs (default: BROKER_URL)",
    )
    serve_parser.add_argument(
        "--audience",
        default="ami",
        help="Expected aud claim of broker-issued JWTs (default: ami)",
    )
    serve_parser.add_argument(
        "--forwarded-allow-ips",
        default="127.0.0.1",
        help="IPs trusted for X-Forwarded-* headers (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--log-level",
        default="info",
        help="uvicorn log level for HTTP transport (default: info)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        serve(
            transport=args.transport,
            host=args.host,
            port=args.port,
            auth=args.auth,
            shared_secret=args.shared_secret,
            resource_url=args.resource_url,
            broker_url=args.broker_url,
            broker_jwks_url=args.broker_jwks_url,
            broker_issuer=args.broker_issuer,
            audience=args.audience,
            forwarded_allow_ips=args.forwarded_allow_ips,
            log_level=args.log_level,
        )
    else:
        parser.print_help()
