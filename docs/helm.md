---
icon: lucide/ship-wheel
---

# Deploying with Helm

The chart at
[`charts/ami-mcp`](https://github.com/kratsg/ami-mcp/tree/main/charts/ami-mcp)
deploys ami-mcp over **HTTP transport** on Kubernetes. It supports the two
hosted auth models the server implements, selected by `auth.mode`:

- **`sharedSecret`** — a single env-built pyAMI client: the pod carries one
  server-managed VOMS proxy (mounted from a Secret you refresh out-of-band) and
  gates every request behind a static bearer token.
- **`broker`** — the AF credential broker: bearers are broker-issued identity
  JWTs verified against the broker's JWKS, and each AMI call redeems the
  caller's own VOMS proxy at the broker. The server holds no AMI credential
  itself, so no proxy is mounted.

There is no published ami-mcp image. An init container runs the
`ghcr.io/prefix-dev/pixi` image and installs the pinned `amiMcp.version` from
conda-forge into a shared volume; the main container then runs `ami-mcp serve`.
The conda-forge package already pulls in `ca-policy-lcg` (which sets
`X509_CERT_DIR` on environment activation), `voms`, `voms-lsc`, and the broker
client library.

## Prerequisites

- A Kubernetes cluster and Helm 3+.
- An ingress controller and (for TLS) cert-manager, if `ingress.enabled` (the
  default). Defaults assume `nginx` + a `letsencrypt-prod` ClusterIssuer.

## Shared-secret mode (server-managed VOMS proxy)

First create the Secrets the pod consumes — the chart never holds the x509
material itself. Provide a VOMS proxy in a Secret you manage and refresh
out-of-band (proxies are short-lived; the chart only consumes the Secret):

```bash
voms-proxy-init -voms atlas
kubectl -n mcp create secret generic ami-x509 \
  --from-file=proxy=/tmp/x509up_u$(id -u)
```

Then install:

```bash
helm install ami-mcp ./charts/ami-mcp \
  --namespace mcp --create-namespace \
  --set ingress.host=ami-mcp.example.com \
  --set auth.sharedSecret.x509.existingSecret=ami-x509 \
  --set auth.sharedSecret.x509.proxyKey=proxy \
  --set auth.sharedSecret.secretValue="$(openssl rand -hex 32)"
```

Notes:

- The proxy is mounted read-only and exported as `X509_USER_PROXY`. pyAMI reads
  only a proxy from the environment — extra keys in the Secret (e.g. a robot
  cert/key used by an out-of-band refresher) are mounted alongside but not wired
  to any env var.
- The CA trust bundle (`X509_CERT_DIR`) is set automatically by `ca-policy-lcg`,
  which ami-mcp already depends on. To force the latest CA bundle, add it to the
  rendered `pixi.toml`: `--set amiMcp.extraPixiDependencies.ca-policy-lcg='*'`.
- Prefer `auth.sharedSecret.existingSecret` (a Secret you create with key
  `shared-secret`) over `secretValue` in production so the token never lands in
  Helm values or CI logs. The bearer always reaches the server via the
  `AMI_MCP_SHARED_SECRET` env var, never argv, keeping it out of the process
  table.

Retrieve the generated bearer and configure clients with it out-of-band:

```bash
kubectl -n mcp get secret ami-mcp-shared-secret \
  -o jsonpath='{.data.shared-secret}' | base64 -d; echo
```

```json
{
  "mcpServers": {
    "ami": {
      "type": "http",
      "url": "https://ami-mcp.example.com/mcp/",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

## Broker mode (per-user VOMS proxies)

```bash
helm install ami-mcp ./charts/ami-mcp \
  --namespace mcp --create-namespace \
  --set ingress.host=ami-mcp.example.com \
  --set auth.mode=broker \
  --set auth.broker.brokerUrl=https://broker.af.example.com
```

The broker URL rides the `AMI_MCP_BROKER_URL` env var; `auth.broker.jwksUrl` and
`auth.broker.issuer` default server-side to values derived from the broker URL,
and `auth.broker.audience` defaults to `ami`. No x509 Secret is mounted in this
mode — per-user proxies are redeemed per call and disposed of immediately.

## PMG cross-section database (CVMFS)

The xsec tools read `PMGxsecDB_<campaign>.txt` files from `ATLAS_PMGXSEC_PATH`
(see [Configuration](configuration.md)). Off by default — without a mount the
xsec tools report the path as unavailable, while all AMI query tools still work.
Provide the files by passing CVMFS through the generic
`extraVolumes`/`extraVolumeMounts` values, which are rendered verbatim into the
pod spec and the main container (any volume source works — PVC, hostPath, CSI,
Secret, ...; fields like `mountPropagation` pass through untouched):

```yaml
ami:
  pmgXsecPath: /cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools
extraVolumes:
  - name: cvmfs
    persistentVolumeClaim:
      claimName: cvmfs
extraVolumeMounts:
  - name: cvmfs
    mountPath: /cvmfs
    mountPropagation: HostToContainer
```

## Monitoring

ami-mcp exposes no `/metrics` endpoint yet, so the chart ships no ServiceMonitor
or Grafana dashboard. They will be added once the server grows a Prometheus
endpoint.

## Security context

`podSecurityContext` and `securityContext` (applied to both the init container
and the main container) are rendered as-is via `toYaml`. The defaults drop all
Linux capabilities and disable privilege escalation, but stop short of
`runAsNonRoot`/`readOnlyRootFilesystem`: the init container installs packages
with `pixi install` and the main container runs `pixi shell-hook`, both of which
currently expect the pixi image's default (root) user and may write outside the
`/workspace` emptyDir. See the commented-out suggestions in `values.yaml` if
you've verified your pixi image tolerates a stricter profile.

## Freezing the deployed version

The chart ships `pixi.toml` (pinning `amiMcp.version`) but **no `pixi.lock`** —
a release must exist before it can be locked, and `pixi install` otherwise
resolves dependencies fresh at each pod start. For reproducible rollouts,
generate a lock against the rendered `pixi.toml` and feed it back in:

```bash
helm template a ./charts/ami-mcp --show-only templates/configmap.yaml \
  --set ingress.host=ami-mcp.example.com \
  --set auth.sharedSecret.secretValue=dummy \
  | yq '.data["pixi.toml"]' > /tmp/pixi.toml
pixi lock --manifest-path /tmp/pixi.toml          # writes /tmp/pixi.lock alongside it
helm upgrade ami-mcp ./charts/ami-mcp --reuse-values \
  --set-file amiMcp.pixiLockContent=/tmp/pixi.lock
```

When `amiMcp.pixiLockContent` is set, the lock is mounted next to `pixi.toml`
and pixi installs from it.

## Verifying and validating the chart

```bash
pixi run -e helm helm-lint       # lint + render both auth modes and the CVMFS passthrough
pixi run -e helm helm-template   # render with default (shared-secret) values
helm test ami-mcp -n mcp         # run the /healthz test hook against a live release
```

## Uninstall

```bash
helm uninstall ami-mcp -n mcp
```

Secrets you created yourself (the x509 Secret, and any `existingSecret` for the
bearer) are not owned by the release and must be removed separately.
