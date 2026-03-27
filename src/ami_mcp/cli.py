"""Command-line interface for ami-mcp."""

from __future__ import annotations

import argparse

from ami_mcp.server import serve


def main() -> None:
    """Entry point for the ami-mcp command."""
    parser = argparse.ArgumentParser(
        prog="ami-mcp",
        description="MCP Server for ATLAS AMI metadata interface",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    subparsers.add_parser(
        "serve",
        help="Start the MCP server (stdio transport)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        serve()
    else:
        parser.print_help()
