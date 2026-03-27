# ami-mcp v0.0.0

[![Actions Status][actions-badge]][actions-link]
[![Documentation Status][rtd-badge]][rtd-link]

[![PyPI version][pypi-version]][pypi-link]
[![PyPI platforms][pypi-platforms]][pypi-link]

[![GitHub Discussion][github-discussions-badge]][github-discussions-link]

[![Coverage][coverage-badge]][coverage-link]

<!-- --8<-- [start:intro] -->

An MCP server that wraps [ATLAS AMI](https://ami.in2p3.fr) (ATLAS Metadata
Interface) and the PMG cross-section database, exposing them as tools for LLMs.
Designed for ATLAS physicists who need to discover MC samples, look up
cross-sections and filter efficiencies, and validate PMG hashtag
classifications.

<!-- --8<-- [end:intro] -->

<!-- --8<-- [start:what-it-does] -->

## What it does

`ami-mcp` lets Claude (or any MCP-compatible LLM) query ATLAS metadata directly:

- **Discover samples**: search for MC datasets by PMG hashtag classification
  (WeakBoson/Vjets/Baseline), by name pattern, or by arbitrary AMI query
- **Look up metadata**: retrieve cross-sections, filter efficiencies, k-factors,
  dataset provenance, and AMI processing tag info
- **Query cross-section DB**: look up DSID entries in the PMG xsec database
  files (PMGxsecDB_mc16.txt, etc.)
- **Validate samples**: check hashtag classifications and compare metadata
  against the PMG cross-section database
- **General queries**: execute arbitrary AMI command strings formulated by the
  LLM using the `ami://query-language` resource as a guide

<!-- --8<-- [end:what-it-does] -->

<!-- --8<-- [start:installation] -->

## Installation

```bash
pip install ami-mcp
```

Or with pixi (recommended for ATLAS facilities):

```bash
pixi add ami-mcp
```

<!-- --8<-- [end:installation] -->

<!-- --8<-- [start:requirements] -->

## Requirements

- Python 3.10 or 3.11 (pyAMI requires `<3.12`)
- A valid VOMS proxy (`voms-proxy-init -voms atlas`)
- Grid CA certificates (available on CVMFS at ATLAS sites)

<!-- --8<-- [end:requirements] -->

<!-- --8<-- [start:quick-start] -->

## Quick start

### 1. Set up authentication

```bash
voms-proxy-init -voms atlas
```

**On CVMFS-based facilities (e.g. UChicago Analysis Facility, CERN lxplus):**

```bash
export X509_CERT_DIR=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates
```

### 2. Test the server

```bash
ami-mcp serve
```

The server speaks MCP over stdio. Configure your MCP client to launch it.

### 3. Configure Claude Code

Add to your `.mcp.json` (project) or `~/.claude.json` (global):

```json
{
  "mcpServers": {
    "ami": {
      "command": "ami-mcp",
      "args": ["serve"],
      "env": {
        "X509_CERT_DIR": "/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates",
        "ATLAS_PMGXSEC_PATH": "/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools"
      }
    }
  }
}
```

### 4. Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "ami": {
      "command": "ami-mcp",
      "args": ["serve"],
      "env": {
        "X509_CERT_DIR": "/path/to/ca-certificates",
        "ATLAS_PMGXSEC_PATH": "/path/to/PMGTools"
      }
    }
  }
}
```

<!-- --8<-- [end:quick-start] -->

<!-- --8<-- [start:tools] -->

## Available tools

### AMI queries

| Tool                   | Description                                                |
| ---------------------- | ---------------------------------------------------------- |
| `ami_execute`          | Execute any AMI command string (primary power tool)        |
| `ami_get_dataset_info` | Get metadata for a dataset (nFiles, nEvents, status, etc.) |
| `ami_get_dataset_prov` | Get provenance chain (EVNT→HITS→RDO→AOD→DAOD)              |
| `ami_list_datasets`    | Search for datasets matching a name pattern                |

### PMG hashtags

| Tool                       | Description                                                          |
| -------------------------- | -------------------------------------------------------------------- |
| `ami_search_by_hashtags`   | Find datasets by hashtag combination (e.g. WeakBoson/Vjets/Baseline) |
| `ami_get_dataset_hashtags` | Look up PMGL1–PMGL4 classification for a dataset                     |

### Physics metadata

| Tool                     | Description                                             |
| ------------------------ | ------------------------------------------------------- |
| `ami_get_physics_params` | Get cross-section, filter efficiency, k-factor from AMI |
| `ami_get_ami_tag`        | Get AMI processing tag info (e.g. e8351, p5855)         |

### Cross-section database

| Tool                      | Description                                                 |
| ------------------------- | ----------------------------------------------------------- |
| `ami_list_xsec_databases` | List available PMGxsecDB\_\*.txt files                      |
| `ami_lookup_xsec`         | Look up DSID cross-section, filter eff, k-factor in xsec DB |

### Validation

| Tool                  | Description                                                  |
| --------------------- | ------------------------------------------------------------ |
| `ami_validate_sample` | Check hashtag classification and compare metadata to xsec DB |

<!-- --8<-- [end:tools] -->

<!-- --8<-- [start:example-prompts] -->

## Example prompts

Once configured, you can ask Claude things like:

- _"Find all Baseline WeakBoson/Vjets samples in mc20_13TeV"_
- _"What are the cross-section and filter efficiency for DSID 700320?"_
- _"Look up the hashtag classification for this EVNT dataset"_
- _"Validate these samples against the mc20 cross-section database"_
- _"Show me the provenance chain for this DAOD dataset"_
- _"What AMI tag e8351 corresponds to — which generator version?"_

<!-- --8<-- [end:example-prompts] -->

<!-- prettier-ignore-start -->
[actions-badge]:            https://github.com/kratsg/ami-mcp/actions/workflows/ci.yml/badge.svg
[actions-link]:             https://github.com/kratsg/ami-mcp/actions
[github-discussions-badge]: https://img.shields.io/static/v1?label=Discussions&message=Ask&color=blue&logo=github
[github-discussions-link]:  https://github.com/kratsg/ami-mcp/discussions
[pypi-link]:                https://pypi.org/project/ami-mcp/
[pypi-platforms]:           https://img.shields.io/pypi/pyversions/ami-mcp
[pypi-version]:             https://img.shields.io/pypi/v/ami-mcp
[rtd-badge]:                https://readthedocs.org/projects/ami-mcp/badge/?version=latest
[rtd-link]:                 https://ami-mcp.readthedocs.io/en/latest/?badge=latest
[coverage-badge]:           https://codecov.io/github/kratsg/ami-mcp/branch/main/graph/badge.svg
[coverage-link]:            https://codecov.io/github/kratsg/ami-mcp

<!-- prettier-ignore-end -->
