---
icon: lucide/code
---

# Contributing

## Architecture

```
LLM <--MCP/stdio--> ami-mcp serve <--HTTPS (pyAMI)--> AMI server (atlas-ami.cern.ch)
                         |
                         +--filesystem--> PMGxsecDB*.txt (cross-section DB on CVMFS)
```

The server uses **pyAMI** directly. Tools call `client.execute(command_string)`
and return formatted text. The LLM reads the `ami://query-language` resource to
learn how to formulate AMI command strings, then calls `ami_execute` with them.

## Development setup

```bash
git clone https://github.com/kratsg/ami-mcp
cd ami-mcp
pixi install
pixi run pre-commit-install
```

## Build and test commands

```bash
pixi run -e py311 test     # quick tests (no live AMI needed)
pixi run -e py311 test-slow  # all tests including live integration
pixi run lint              # pre-commit + pylint
pixi run build             # build sdist + wheel
pixi run docs-serve        # build and serve docs locally
```

## Tool registration pattern

Each tool module lives in `src/ami_mcp/tools/` and exports a single
`register(mcp: FastMCP) -> None` function. Tools are defined as closures inside
`register()` using the `@mcp.tool()` decorator.

```python
# tools/mymodule.py
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ami_mcp.tools._helpers import (
    append_next_actions,
    format_ami_result,
    format_error,
    run_ami_sync,
)


def register(mcp: FastMCP) -> None:
    """Register my tools with the MCP server."""

    @mcp.tool()
    async def ami_my_tool(param: str, *, ctx: Context[Any, Any]) -> str:
        """One-line summary shown to the LLM as the tool purpose.

        Longer description. Explain what AMI command this wraps and
        what the output looks like.

        Args:
            param: Description of the parameter.
        """
        client = ctx.request_context.lifespan_context["ami_client"]
        try:
            result = await run_ami_sync(
                client.execute,
                f'SomeAMICommand -param="{param}"',
                format="dom_object",
            )
            rows = result.get_rows()
            output = format_ami_result(rows)
            return append_next_actions(
                output, ["Use `ami_get_dataset_info` for full metadata."]
            )
        except Exception as exc:  # noqa: BLE001
            return format_error(
                exc,
                hints=[
                    "Check the parameter format.",
                    "Use `ami_execute` for raw queries.",
                ],
            )
```

Key conventions:

- Tool names are prefixed with `ami_` to avoid collisions
- `ctx` is keyword-only (after `*`)
- Errors are returned via `format_error(exc, hints=[...])` — never raised as
  exceptions and never as bare `f"Error: {exc}"` strings
- Use `append_next_actions(output, [...])` to suggest follow-up tool calls after
  a successful result
- **Do NOT import `pyAMI_atlas.api` in tool modules** — `pyAMI/utils.py` has an
  invalid escape sequence that becomes a SyntaxError under
  `filterwarnings=["error"]` on Python 3.11+. Use `client.execute(cmd)`
  directly.
- All `client.execute()` calls go through `run_ami_sync()` (wraps blocking pyAMI
  HTTP calls in `asyncio.to_thread()`)

To wire a new module into the server, add it to the import and loop in
`server.py`:

```python
from ami_mcp.tools import mymodule

for _module in [..., mymodule]:
    _module.register(mcp)
```

## Tests

All tools have unit tests using mocked fixtures from `tests/conftest.py`:

- `mock_ami_client` — a `MagicMock` with `.execute.return_value` pre-configured
- `mock_ctx` — an async context with `ami_client` in `lifespan_context`

Tests mock `run_ami_sync` (not `client.execute` directly) and return a MagicMock
with `.get_rows.return_value = [...]`.

```python
# tests/test_tools_mymodule.py
from __future__ import annotations

from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from ami_mcp.tools.mymodule import register


@pytest.fixture
def registered_tools(mock_ctx):
    mcp = FastMCP("test")
    register(mcp)
    return {t.name: t.fn for t in mcp._tool_manager.list_tools()}


class TestAmiMyTool:
    async def test_basic(self, registered_tools, mock_ctx):
        rows = [OrderedDict([("key", "value")])]
        result_mock = MagicMock()
        result_mock.get_rows.return_value = rows
        with patch(
            "ami_mcp.tools.mymodule.run_ami_sync",
            new=AsyncMock(return_value=result_mock),
        ):
            result = await registered_tools["ami_my_tool"]("param", ctx=mock_ctx)
        assert "value" in result
```

## Testing on the UChicago Analysis Facility

1. SSH to the facility and initialise your proxy:

   ```bash
   voms-proxy-init -voms atlas
   # X509_CERT_DIR is set automatically when using pixi (ca-policy-lcg); otherwise:
   export X509_CERT_DIR=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates
   ```

2. Start the server:

   ```bash
   # With pixi (X509_CERT_DIR set automatically):
   ATLAS_PMGXSEC_PATH=/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools \
       pixi run ami-mcp serve

   # With pip (set X509_CERT_DIR manually):
   env X509_CERT_DIR=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates \
       ATLAS_PMGXSEC_PATH=/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools \
       ami-mcp serve
   ```

3. Run integration tests:

   ```bash
   pytest tests/integration/ --runslow -v
   ```
