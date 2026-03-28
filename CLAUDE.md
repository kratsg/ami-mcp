# ami-mcp — Contributor Guide

MCP server that wraps ATLAS AMI (ATLAS Metadata Interface) and the PMG
cross-section database, exposing them as tools for LLMs.

## Architecture

```
LLM <--MCP/stdio--> ami-mcp serve <--HTTPS (pyAMI)--> AMI server (atlas-ami.cern.ch)
                         |
                         +--filesystem--> PMGxsecDB*.txt (cross-section DB on CVMFS)
```

**Design philosophy**: MCP resources document the AMI query DSL. The LLM reads
those resources, formulates AMI command strings itself, then calls tools like
`ami_execute` with those strings. We do NOT hide query construction behind
hundreds of wrappers — instead we give the LLM the DSL and let it be expressive.

## Project layout

```
src/ami_mcp/
├── __init__.py          # version
├── _version.pyi         # type stub
├── py.typed
├── cli.py               # argparse: `ami-mcp serve`
├── server.py            # FastMCP setup, lifespan (pyAMI client init), tool registration
├── nomenclature.py      # ATLAS naming + hashtag + campaign constants (used by resources.py)
├── resources.py         # MCP resources: AMI query language ref, nomenclature, commands
└── tools/
    ├── __init__.py
    ├── _helpers.py      # format_ami_result(), run_ami_sync(), scope_to_catalog()
    ├── execute.py       # ami_execute (general purpose AMI command execution)
    ├── datasets.py      # ami_get_dataset_info, ami_list_datasets, ami_get_dataset_prov
    ├── hashtags.py      # ami_search_by_hashtags, ami_get_dataset_hashtags
    ├── physics.py       # ami_get_physics_params
    ├── tags.py          # ami_get_ami_tag
    ├── xsecdb.py        # ami_list_xsec_databases, ami_lookup_xsec
    └── validate.py      # ami_validate_sample
tests/
├── conftest.py               # mock_ami_client, mock_ctx fixtures
├── test_package.py
├── test_cli.py
├── test_server.py
├── test_resources.py
├── test_tools_execute.py
├── test_tools_datasets.py
├── test_tools_hashtags.py
├── test_tools_physics.py
├── test_tools_tags.py
├── test_tools_xsecdb.py
└── integration/test_live.py  # requires live AMI access, run with --runslow
```

## Tool registration pattern

Each tool module exports a `register(mcp: FastMCP) -> None` function.
`server.py` imports the modules and calls `module.register(mcp)` for each. Tools
are defined as closures inside `register()` using the `@mcp.tool()` decorator.

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
    @mcp.tool()
    async def ami_my_tool(param: str, *, ctx: Context[Any, Any]) -> str:
        """Tool description — shown to the LLM as the tool's purpose."""
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
- `ctx` is keyword-only (after `*`) so optional parameters can have defaults
  before it
- Errors are returned via `format_error(exc, hints=[...])` — never raised as
  exceptions and never as bare `f"Error: {exc}"` strings
- Use `append_next_actions(output, [...])` to suggest follow-up tool calls
- `except Exception as exc:` lines carry `# noqa: BLE001` inline;
  `broad-exception-caught` is disabled globally in pylint (`pyproject.toml`)
- All pyAMI calls go through `run_ami_sync()` — pyAMI's HTTP client is
  synchronous (httplib); wrapping with `asyncio.to_thread()` prevents blocking
  the MCP event loop
- **Do NOT import `pyAMI_atlas.api` in tool modules.** `pyAMI/utils.py` has an
  invalid escape sequence (`'\W+'`) that becomes a SyntaxError under
  `filterwarnings=["error"]` on Python 3.11+. Use `client.execute(cmd_string)`
  directly instead.

Then wire it in `server.py`:

```python
from ami_mcp.tools import mymodule

for _module in [..., mymodule]:
    _module.register(mcp)
```

## Build and test commands

```bash
pixi run test          # quick tests (no live AMI needed)
pixi run test-slow     # all tests including live integration (requires AMI auth)
pixi run lint          # pre-commit + pylint
pixi run build         # build sdist + wheel
pixi run build-check   # verify the built distributions with twine
```

## Development setup

```bash
pixi install           # install all dependencies
pixi run pre-commit-install  # install git hooks
```

## Adding a new tool

1. Decide which module it belongs to (or create a new one).
2. Add a new `@mcp.tool()` function inside the module's `register()`.
3. If creating a new module, add it to the loop in `server.py`.
4. Write unit tests using `mock_ami_client` and `mock_ctx` from conftest.
5. Run `pixi run test` to verify.

## pyAMI client reference

Two packages: `pyAMI-core` (the HTTP client) and `pyAMI-atlas` (ATLAS endpoint
registration). Importing `pyAMI_atlas` (or `pyAMI_atlas.api`) has a side-effect
of registering ATLAS endpoints and table schemas with the core client.

**Client construction** (in `server.py` lifespan only):

```python
import pyAMI.client
import pyAMI_atlas.api as _atlas_api  # noqa: F401  (registers ATLAS endpoints)

client = pyAMI.client.Client("atlas-replica")
```

**Core method** (used in all tool functions):

```python
result = await run_ami_sync(client.execute, command_string, format="dom_object")
rows = result.get_rows()  # list of OrderedDicts
rows = result.get_rows("node")  # provenance node rows
rows = result.get_rows("edge")  # provenance edge rows
```

**pypi install note**: `pyAMI-atlas` imports `pyAMI-core` at build time without
declaring it. In `pixi.toml` both must be listed in `[pypi-dependencies]` and
`pyami-atlas` must be in `[pypi-options] no-build-isolation`.

## AMI command patterns

All tools use `client.execute(command_string, format="dom_object")`. Common
command patterns:

```
# Dataset info
AMIGetDatasetInfo -logicalDatasetName="mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"

# Dataset provenance
AMIGetDatasetProv -logicalDatasetName="..." -depth="10"

# List datasets (note: no double-quotes around catalog/entity; LIMIT 0,N not LIMIT N)
SearchQuery -catalog=mc15_001:production -entity=dataset
  -mql="SELECT logicalDatasetName, nFiles, nEvents WHERE physicsShort LIKE '%Zee%' LIMIT 0,50"

# AMI processing tag info (pass single tag; split "e8351_s3681" → look up "e8351" first)
AMIGetAMITagInfo -amiTag="e8351"

# Physics parameters (cross-section, filter eff, k-factor — pass EVNT LDN)
GetPhysicsParamsForDataset -logicalDatasetName="..."

# Hashtag classification (pass EVNT LDN)
DatasetWBListHashtags -ldn="mc20_13TeV.700320.Sh_2211_Zee.evgen.EVNT.e8351"

# Datasets for hashtag combination (returns all campaigns; filter ldn client-side)
DatasetWBListDatasetsForHashtag -scope="PMGL1,PMGL2,PMGL3" -name="WeakBoson,Vjets,Baseline" -operator="AND"

# General SearchQuery (LLM-formulated; no double-quotes around catalog/entity)
SearchQuery -catalog=mc23_001:production -entity=HASHTAGS
  -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL1'"
```

**Important SearchQuery quoting rule**: Do NOT double-quote `-catalog` or
`-entity` values. Quoting them causes parse errors when the MQL contains `%`
wildcards. Only `-mql` needs quoting. Use `LIMIT 0,N` syntax (not `LIMIT N`).

Catalog names depend on scope:

- `mc16_13TeV`, `mc20_13TeV` → `mc15_001:production`
- `mc23_13p6TeV` → `mc23_001:production`

## ATLAS dataset nomenclature

Full reference: ATL-COM-GEN-2007-003 "ATLAS Dataset Nomenclature" (2024
edition), available at https://cds.cern.ch/record/1070318

**Monte Carlo (Logical Dataset Name):**

```
project.datasetNumber.physicsShort.prodStep.dataType.AMITags
mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.deriv.DAOD_PHYS.e8351_s3681_r13144_r13146_p5855
```

**Real data (primary):**

```
project.runNumber.streamName.prodStep.dataType.AMITags
data18_13TeV.00348885.physics_Main.deriv.DAOD_PHYS.r13286_p4910_p5855
```

AMI tag letters: `e`=evgen, `s`=simul, `d`=digit, `r`=reco(ProdSys),
`f`=reco(Tier0), `p`=group-production/deriv, `m`=merge(Tier0),
`t`=merge(ProdSys)

Common data types: `DAOD_PHYS`, `DAOD_PHYSLITE` (most common for analysis),
`DAOD_EXOT*`, `DAOD_SUSY*`, `AOD`, `ESD`, `EVNT`, `HITS`, `RDO`

## PMG hashtag system

Datasets in AMI are classified with up to 4 hashtag levels:

- **PMGL1** — Physics process subgroup (e.g. `WeakBoson`, `Top`, `Higgs`)
- **PMGL2** — Sample type (e.g. `Vjets`, `ttbar`)
- **PMGL3** — Status (e.g. `Baseline`, `Systematic`, `Alternative`, `Obsolete`)
- **PMGL4** — Generator (e.g. `Sherpa`, `Powheg`)

Query via `DatasetWBListHashtags -ldn="..."` or search via
`DatasetWBListDatasetsForHashtag -scope="..." -l1tag="..." [-l2tag="..."] ...`

## PMG cross-section database

Files at `ATLAS_PMGXSEC_PATH` (default:
`/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools`):

- Named `PMGxsecDB_<campaign>.txt` (e.g. `PMGxsecDB_mc16.txt`)
- Tab-separated values
- Header line uses `:` to separate `colName/TYPE` entries:
  `dataset_number/I:physics_short/C:crossSection_pb/D:genFiltEff/D:kFactor/D:...`
- Column types: `/I` = int, `/C` = string, `/D` = float
- Newer files (mc16+): `crossSection_pb` column (already in pb)
- Older files: `crossSection` column (in nb, multiply ×1000 for pb)
- Multiple rows per DSID when different etags exist

## Testing on the UChicago Analysis Facility

1. SSH to the facility and set up your environment:

   ```bash
   voms-proxy-init -voms atlas
   export X509_USER_PROXY=$(voms-proxy-info --path)
   ```

2. Install ami-mcp from source:

   ```bash
   pip install -e .
   ```

3. Start the server:

   With pixi (`X509_CERT_DIR` is set automatically by `ca-policy-lcg`):

   ```bash
   env X509_USER_PROXY=/tmp/x509up_u$(id -u) \
       ATLAS_PMGXSEC_PATH=/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools \
       pixi run ami-mcp serve
   ```

   With pip (must set `X509_CERT_DIR` manually):

   ```bash
   env X509_USER_PROXY=/tmp/x509up_u$(id -u) \
       X509_CERT_DIR=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates \
       ATLAS_PMGXSEC_PATH=/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools \
       ami-mcp serve
   ```

4. Example Claude Code MCP config (`.mcp.json`):

   With pixi:

   ```json
   {
     "mcpServers": {
       "ami": {
         "type": "stdio",
         "command": "pixi",
         "args": ["run", "ami-mcp", "serve"],
         "env": {
           "ATLAS_PMGXSEC_PATH": "/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools"
         }
       }
     }
   }
   ```

   With pip:

   ```json
   {
     "mcpServers": {
       "ami": {
         "command": "ami-mcp",
         "args": ["serve"],
         "env": {
           "X509_USER_PROXY": "/tmp/x509up_u1000",
           "X509_CERT_DIR": "/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates",
           "ATLAS_PMGXSEC_PATH": "/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools"
         }
       }
     }
   }
   ```

5. Run integration tests:

   ```bash
   pytest tests/integration/ --runslow -v
   ```
