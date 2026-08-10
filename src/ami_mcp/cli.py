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
            shared_secret=args.shared_secret,
            resource_url=args.resource_url,
            forwarded_allow_ips=args.forwarded_allow_ips,
            log_level=args.log_level,
        )
    else:
        parser.print_help()
