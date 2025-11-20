{{/*
================================================================================
Screenshot API Helpers
================================================================================
*/}}

{{/*
Expand the name of the screenshot-api.
*/}}
{{- define "geosnappro.screenshotApi.name" -}}
{{- default "screenshot-api" .Values.screenshotApi.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name for screenshot-api.
*/}}
{{- define "geosnappro.screenshotApi.fullname" -}}
{{- if .Values.screenshotApi.fullnameOverride -}}
{{- .Values.screenshotApi.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "screenshot-api" .Values.screenshotApi.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Common Labels for screenshot-api
*/}}
{{- define "geosnappro.screenshotApi.labels" -}}
app.kubernetes.io/name: {{ include "geosnappro.screenshotApi.name" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: screenshot-api
app.kubernetes.io/part-of: geosnappro
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for screenshot-api
*/}}
{{- define "geosnappro.screenshotApi.selectorLabels" -}}
app: {{ include "geosnappro.screenshotApi.fullname" . }}
app.kubernetes.io/name: {{ include "geosnappro.screenshotApi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: screenshot-api
{{- end -}}

{{/*
Service account name for screenshot-api
*/}}
{{- define "geosnappro.screenshotApi.serviceAccountName" -}}
{{- if .Values.screenshotApi.serviceAccount.create -}}
{{- if .Values.screenshotApi.serviceAccount.name -}}
{{- .Values.screenshotApi.serviceAccount.name -}}
{{- else -}}
{{- include "geosnappro.screenshotApi.fullname" . -}}
{{- end -}}
{{- else -}}
{{- default "default" .Values.screenshotApi.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
================================================================================
Gluetun API Helpers
================================================================================
*/}}

{{/*
Expand the name of the gluetun-api.
*/}}
{{- define "geosnappro.gluetunApi.name" -}}
{{- default "gluetun-api" .Values.gluetunApi.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name for gluetun-api.
*/}}
{{- define "geosnappro.gluetunApi.fullname" -}}
{{- if .Values.gluetunApi.fullnameOverride -}}
{{- .Values.gluetunApi.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "gluetun-api" .Values.gluetunApi.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Common Labels for gluetun-api
*/}}
{{- define "geosnappro.gluetunApi.labels" -}}
app.kubernetes.io/name: {{ include "geosnappro.gluetunApi.name" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: gluetun-api
app.kubernetes.io/part-of: geosnappro
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for gluetun-api
*/}}
{{- define "geosnappro.gluetunApi.selectorLabels" -}}
app: {{ include "geosnappro.gluetunApi.fullname" . }}
app.kubernetes.io/name: {{ include "geosnappro.gluetunApi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: gluetun-api
{{- end -}}

{{/*
Service account name for gluetun-api
*/}}
{{- define "geosnappro.gluetunApi.serviceAccountName" -}}
{{- if .Values.gluetunApi.serviceAccount.create -}}
{{- if .Values.gluetunApi.serviceAccount.name -}}
{{- .Values.gluetunApi.serviceAccount.name -}}
{{- else -}}
{{- include "geosnappro.gluetunApi.fullname" . -}}
{{- end -}}
{{- else -}}
{{- default "default" .Values.gluetunApi.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
================================================================================
Frontend Helpers
================================================================================
*/}}

{{/*
Expand the name of the frontend.
*/}}
{{- define "geosnappro.frontend.name" -}}
{{- default "frontend" .Values.frontend.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name for frontend.
*/}}
{{- define "geosnappro.frontend.fullname" -}}
{{- if .Values.frontend.fullnameOverride }}
{{- .Values.frontend.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "frontend" .Values.frontend.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "geosnappro.frontend.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels for frontend
*/}}
{{- define "geosnappro.frontend.labels" -}}
helm.sh/chart: {{ include "geosnappro.frontend.chart" . }}
{{ include "geosnappro.frontend.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/component: frontend
app.kubernetes.io/part-of: geosnappro
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels for frontend
*/}}
{{- define "geosnappro.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "geosnappro.frontend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Create the name of the service account to use for frontend
*/}}
{{- define "geosnappro.frontend.serviceAccountName" -}}
{{- if .Values.frontend.serviceAccount.create }}
{{- default (include "geosnappro.frontend.fullname" .) .Values.frontend.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.frontend.serviceAccount.name }}
{{- end }}
{{- end }}

