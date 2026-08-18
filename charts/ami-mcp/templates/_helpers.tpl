{{/*
Expand the name of the chart.
*/}}
{{- define "ami-mcp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ami-mcp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart name and version label value.
*/}}
{{- define "ami-mcp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ami-mcp.labels" -}}
helm.sh/chart: {{ include "ami-mcp.chart" . }}
{{ include "ami-mcp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels. Kept stable (name + instance) so external selectors keyed on
app.kubernetes.io/name=ami-mcp continue to match.
*/}}
{{- define "ami-mcp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ami-mcp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name to use.
*/}}
{{- define "ami-mcp.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ami-mcp.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Name of the Secret holding the shared bearer (existing or chart-created).
*/}}
{{- define "ami-mcp.sharedSecretName" -}}
{{- if .Values.auth.sharedSecret.existingSecret -}}
{{- .Values.auth.sharedSecret.existingSecret -}}
{{- else -}}
{{- printf "%s-shared-secret" (include "ami-mcp.fullname" .) -}}
{{- end -}}
{{- end }}

{{/*
Validate the auth configuration. Fails the render early with a clear message
rather than producing a manifest the server would reject at startup.
*/}}
{{- define "ami-mcp.validate" -}}
{{- if eq .Values.auth.mode "sharedSecret" -}}
  {{- $ss := .Values.auth.sharedSecret -}}
  {{- if and (not $ss.existingSecret) (not $ss.secretValue) -}}
    {{- fail "auth.mode=sharedSecret requires auth.sharedSecret.existingSecret or auth.sharedSecret.secretValue" -}}
  {{- end -}}
  {{- if and $ss.x509.existingSecret (not $ss.x509.proxyKey) -}}
    {{- fail "auth.sharedSecret.x509.existingSecret requires auth.sharedSecret.x509.proxyKey (pyAMI reads only X509_USER_PROXY)" -}}
  {{- end -}}
{{- else if eq .Values.auth.mode "broker" -}}
  {{- if not .Values.auth.broker.brokerUrl -}}
    {{- fail "auth.mode=broker requires auth.broker.brokerUrl" -}}
  {{- end -}}
{{- else -}}
  {{- fail (printf "auth.mode must be 'sharedSecret' or 'broker', got %q" .Values.auth.mode) -}}
{{- end -}}
{{- end }}

{{/*
Public resource URL: explicit value, else derived from the ingress host, else
empty (the server falls back to http://<host>:<port>).
*/}}
{{- define "ami-mcp.resourceUrl" -}}
{{- if .Values.server.resourceUrl -}}
{{- .Values.server.resourceUrl -}}
{{- else if and .Values.ingress.enabled .Values.ingress.host -}}
{{- printf "https://%s" .Values.ingress.host -}}
{{- end -}}
{{- end }}

{{/*
Build the `ami-mcp serve` argument string from values. The shared bearer is
passed via the AMI_MCP_SHARED_SECRET env var (not a flag) to keep it out of
the process table; likewise the broker URL rides AMI_MCP_BROKER_URL.
*/}}
{{- define "ami-mcp.serveArgs" -}}
{{- include "ami-mcp.validate" . -}}
{{- $args := list "--transport" "http"
    "--host" (.Values.server.host | toString)
    "--port" (.Values.server.port | toString)
    "--forwarded-allow-ips" (printf "'%s'" .Values.forwardedAllowIps)
    "--log-level" .Values.logLevel -}}
{{- if eq .Values.auth.mode "broker" -}}
{{- $args = append $args "--auth" -}}
{{- $args = append $args "broker" -}}
{{- with .Values.auth.broker.jwksUrl -}}
{{- $args = append $args "--broker-jwks-url" -}}
{{- $args = append $args . -}}
{{- end -}}
{{- with .Values.auth.broker.issuer -}}
{{- $args = append $args "--broker-issuer" -}}
{{- $args = append $args . -}}
{{- end -}}
{{- $args = append $args "--audience" -}}
{{- $args = append $args .Values.auth.broker.audience -}}
{{- else -}}
{{- $args = append $args "--auth" -}}
{{- $args = append $args "shared-secret" -}}
{{- end -}}
{{- with (include "ami-mcp.resourceUrl" .) -}}
{{- $args = append $args "--resource-url" -}}
{{- $args = append $args . -}}
{{- end -}}
{{- $args | join " " -}}
{{- end }}
