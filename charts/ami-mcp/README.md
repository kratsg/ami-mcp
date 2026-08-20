# ami-mcp Helm chart

Deploys [ami-mcp](https://github.com/kratsg/ami-mcp) over **HTTP transport** on
Kubernetes, in one of two auth models selected by `auth.mode`:

- **`sharedSecret`** — a single env-built pyAMI client (a server-managed VOMS
  proxy you mount into the pod) gated by a static bearer token.
- **`broker`** — the AF credential broker: bearers are broker-issued JWTs, and a
  per-user VOMS proxy is redeemed per call. The server holds no AMI credential
  itself.

There is no published ami-mcp container image: an init container runs the
`ghcr.io/prefix-dev/pixi` image and installs the pinned `amiMcp.version` from
conda-forge into a shared volume at pod startup.

## Quick start

```bash
# shared-secret: server-managed VOMS proxy + static bearer
kubectl -n mcp create secret generic ami-x509 \
  --from-file=proxy=/tmp/x509up_u$(id -u)

helm install ami-mcp ./charts/ami-mcp \
  --namespace mcp --create-namespace \
  --set ingress.host=ami-mcp.example.com \
  --set auth.sharedSecret.x509.existingSecret=ami-x509 \
  --set auth.sharedSecret.x509.proxyKey=proxy \
  --set auth.sharedSecret.secretValue="$(openssl rand -hex 32)"
```

```bash
# broker: per-user VOMS proxies via the AF credential broker
helm install ami-mcp ./charts/ami-mcp \
  --namespace mcp --create-namespace \
  --set ingress.host=ami-mcp.example.com \
  --set auth.mode=broker \
  --set auth.broker.brokerUrl=https://broker.af.example.com
```

## Values

| Key                                         | Default                   | Description                                                            |
| ------------------------------------------- | ------------------------- | ---------------------------------------------------------------------- |
| `image.repository`                          | `ghcr.io/prefix-dev/pixi` | Image the init + main containers run (no published ami-mcp image)      |
| `image.tag`                                 | `0.69.0-jammy`            | pixi image tag                                                         |
| `image.pullPolicy`                          | `IfNotPresent`            | Image pull policy                                                      |
| `imagePullSecrets`                          | `[]`                      | Pull secrets for the pixi image                                        |
| `amiMcp.version`                            | `0.2.4`                   | ami-mcp release pinned into the rendered `pixi.toml`                   |
| `amiMcp.extraPixiDependencies`              | `{}`                      | Extra conda-forge deps merged into `pixi.toml` (name -> spec)          |
| `amiMcp.pixiLockContent`                    | `""`                      | Frozen `pixi.lock` for reproducible installs (`--set-file`)            |
| `replicaCount`                              | `1`                       | Deployment replicas                                                    |
| `logLevel`                                  | `info`                    | uvicorn log level (`--log-level`)                                      |
| `forwardedAllowIps`                         | `"*"`                     | IPs trusted for X-Forwarded-\* headers (`--forwarded-allow-ips`)       |
| `server.host`                               | `0.0.0.0`                 | Bind address (`--host`)                                                |
| `server.port`                               | `8000`                    | MCP HTTP port, also serves `/healthz` (`--port`)                       |
| `server.resourceUrl`                        | `""`                      | Public URL (`--resource-url`); derived from `ingress.host` if empty    |
| `ami.endpoint`                              | `atlas-replica`           | AMI server endpoint (`AMI_ENDPOINT`)                                   |
| `ami.pmgXsecPath`                           | `""`                      | `ATLAS_PMGXSEC_PATH`; empty = server default (CVMFS PMGTools dir)      |
| `extraVolumes`                              | `[]`                      | Extra `corev1.Volume`s rendered verbatim into the pod spec             |
| `extraVolumeMounts`                         | `[]`                      | Extra `corev1.VolumeMount`s rendered verbatim into the main container  |
| `auth.mode`                                 | `sharedSecret`            | `sharedSecret` or `broker`                                             |
| `auth.sharedSecret.existingSecret`          | `""`                      | Secret holding the bearer under key `shared-secret`                    |
| `auth.sharedSecret.secretValue`             | `""`                      | Bearer value if no `existingSecret` (chart creates the Secret)         |
| `auth.sharedSecret.x509.existingSecret`     | `""`                      | Secret with the VOMS proxy (and any extra x509 material)               |
| `auth.sharedSecret.x509.proxyKey`           | `""`                      | Key in that Secret mounted as `X509_USER_PROXY`                        |
| `auth.sharedSecret.x509.mountPath`          | `/etc/grid-security/ami`  | Where the x509 Secret is mounted (read-only)                           |
| `auth.sharedSecret.x509CertDir`             | `""`                      | `X509_CERT_DIR` override; usually unset (`ca-policy-lcg` sets it)      |
| `auth.broker.brokerUrl`                     | `""`                      | AF broker base URL (required in broker mode; env `AMI_MCP_BROKER_URL`) |
| `auth.broker.jwksUrl`                       | `""`                      | JWKS URL (`--broker-jwks-url`); empty = derived from `brokerUrl`       |
| `auth.broker.issuer`                        | `""`                      | Expected `iss` claim (`--broker-issuer`); empty = `brokerUrl`          |
| `auth.broker.audience`                      | `ami`                     | Expected `aud` claim (`--audience`)                                    |
| `extraEnv`                                  | `[]`                      | Extra `corev1.EnvVar`s for the main container                          |
| `ingress.enabled`                           | `true`                    | Create an Ingress                                                      |
| `ingress.className`                         | `nginx`                   | Ingress class                                                          |
| `ingress.host`                              | `""`                      | External hostname (required when `ingress.enabled`)                    |
| `ingress.annotations`                       | cert-manager issuer       | Ingress annotations                                                    |
| `ingress.tls.enabled`                       | `true`                    | Enable TLS on the Ingress                                              |
| `ingress.tls.secretName`                    | `""`                      | TLS Secret name; defaults to `<fullname>-tls`                          |
| `service.type`                              | `ClusterIP`               | Service type                                                           |
| `service.port`                              | `80`                      | Service port mapped to `server.port`                                   |
| `serviceAccount.create`                     | `false`                   | Create a ServiceAccount                                                |
| `serviceAccount.name`                       | `""`                      | ServiceAccount name (default SA when empty and not created)            |
| `serviceAccount.annotations`                | `{}`                      | ServiceAccount annotations                                             |
| `resources` / `initResources`               | see values                | Main / pixi-install container resources                                |
| `podAnnotations` / `podLabels`              | `{}`                      | Extra pod metadata                                                     |
| `nodeSelector` / `tolerations` / `affinity` | `{}` / `[]` / `{}`        | Scheduling controls                                                    |
| `podSecurityContext`                        | `{}`                      | Pod-level securityContext (verbatim)                                   |
| `securityContext`                           | drop-all, no-priv-esc     | Container securityContext for init + main containers                   |

There is no ServiceMonitor or Grafana dashboard: ami-mcp exposes no `/metrics`
endpoint yet.

## Mounting CVMFS for the PMG cross-section DB

The xsec tools read `PMGxsecDB_<campaign>.txt` files from `ATLAS_PMGXSEC_PATH`.
Provide them by passing CVMFS through the generic
`extraVolumes`/`extraVolumeMounts` mechanism (any volume source works — PVC,
hostPath, CSI, ...; fields like `mountPropagation` pass through verbatim):

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

Without a CVMFS mount the xsec tools report the path as unavailable; all AMI
query tools still work.

## Freezing the deployed version

By default `pixi install` resolves dependencies fresh at each pod start. For
reproducible rollouts, generate a lock against the rendered `pixi.toml` after a
release and feed it back in:

```bash
helm template a ./charts/ami-mcp --show-only templates/configmap.yaml \
  --set ingress.host=ami-mcp.example.com \
  --set auth.sharedSecret.secretValue=dummy \
  | yq '.data["pixi.toml"]' > /tmp/pixi.toml
pixi lock --manifest-path /tmp/pixi.toml          # writes /tmp/pixi.lock
helm upgrade ami-mcp ./charts/ami-mcp \
  --reuse-values --set-file amiMcp.pixiLockContent=/tmp/pixi.lock
```

Full documentation: see the project docs, "Deploying with Helm".
