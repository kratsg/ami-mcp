---
icon: lucide/settings
---

# Configuration

## Environment variables

| Variable             | Required    | Description                                                                   |
| -------------------- | ----------- | ----------------------------------------------------------------------------- |
| `X509_USER_PROXY`    | Recommended | Path to your VOMS proxy certificate (auto-detected from `/tmp/x509up_u<uid>`) |
| `X509_CERT_DIR`      | Recommended | Directory of CA certificates for SSL verification                             |
| `AMI_ENDPOINT`       | No          | AMI server endpoint (default: `atlas-replica`)                                |
| `ATLAS_PMGXSEC_PATH` | No          | Path to PMGxsecDB text files (default: CVMFS PMGTools directory)              |

## Authentication

`ami-mcp` uses VOMS proxy certificates for ATLAS grid authentication. pyAMI
auto-detects the proxy from `X509_USER_PROXY` or the default path
`/tmp/x509up_u<uid>`.

### Obtaining a VOMS proxy

```bash
voms-proxy-init -voms atlas
```

Check validity:

```bash
voms-proxy-info --all
```

### On CVMFS-based facilities (UChicago AF, CERN lxplus, etc.)

```bash
voms-proxy-init -voms atlas
export X509_CERT_DIR=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/etc/grid-security-emi/certificates
export ATLAS_PMGXSEC_PATH=/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools
```

## Startup preflight checks

`ami-mcp serve` runs preflight checks and warns if required configuration is
missing (but does not exit — the server starts regardless so you can test
connectivity).

**Missing proxy (warning):**

```
[ami-mcp] WARNING: no VOMS proxy found at /tmp/x509up_u1000.
    AMI authentication will fail. Run: voms-proxy-init -voms atlas
```

**Missing `X509_CERT_DIR` (warning):**

```
[ami-mcp] WARNING: X509_CERT_DIR is not set.
    SSL certificate verification may fail when contacting the AMI server.
```

## AMI endpoint

The default endpoint `atlas-replica` is a read-only replica of the main AMI
server. For write operations (not currently exposed), set `AMI_ENDPOINT=atlas`.

```bash
export AMI_ENDPOINT=atlas-replica   # default, recommended for queries
```

## Cross-section database path

The PMG cross-section database files are tab-separated text files named
`PMGxsecDB_<campaign>.txt`. On ATLAS facilities they live on CVMFS:

```
/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools/PMGxsecDB_mc16.txt
/cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools/PMGxsecDB_mc23.txt
...
```

If `ATLAS_PMGXSEC_PATH` is not set, `ami_list_xsec_databases` and
`ami_lookup_xsec` will use this default path. Set it to an alternative location
if you have a local copy.
