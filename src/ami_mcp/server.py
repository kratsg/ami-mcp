"""FastMCP server setup for ami-mcp."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from mcp.server.fastmcp import FastMCP

from ami_mcp.nomenclature import ATLAS_NOMENCLATURE, AMI_QUERY_LANGUAGE
from ami_mcp.resources import register as register_resources
from ami_mcp.tools import datasets, execute, hashtags, physics, tags, validate, xsecdb

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
        default_proxy = Path(f"/tmp/x509up_u{uid}")  # noqa: S108
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


def _make_mcp() -> FastMCP:
    """Build and return a configured FastMCP instance."""

    @asynccontextmanager
    async def _lifespan(_server: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
        """Initialize the pyAMI client for the lifetime of the MCP server.

        The client reads the VOMS proxy from X509_USER_PROXY or the default
        /tmp/x509up_u<uid> path. Set X509_CERT_DIR for SSL cert verification.
        """
        import pyAMI.client
        import pyAMI_atlas.api as _atlas_api  # noqa: F401 (side-effect: registers ATLAS endpoints)

        endpoint = os.environ.get("AMI_ENDPOINT", "atlas-replica")
        client = pyAMI.client.Client(endpoint)
        yield {"ami_client": client}

    mcp = FastMCP("ami-mcp", lifespan=_lifespan, instructions=_INSTRUCTIONS)

    for _module in [execute, datasets, hashtags, physics, tags, xsecdb, validate]:
        _module.register(mcp)

    register_resources(mcp)

    return mcp


def serve() -> None:
    """Start the MCP server over stdio."""
    _preflight_check()
    _make_mcp().run(transport="stdio")
