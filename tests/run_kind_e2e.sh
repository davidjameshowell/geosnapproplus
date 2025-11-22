#!/bin/bash

# Kind-based end-to-end integration test runner for the Geosnap stack.
# This script provisions a local Kind cluster, loads freshly built images
# for the frontend, screenshot API, and Gluetun API, and deploys the UNIFIED
# Helm chart (charts/geosnappro) that includes all three services.
# Then runs pytest-based smoke checks that exercise their health endpoints.
#
# Behavior with existing cluster:
#   If the cluster already exists, the script will:
#   1. Rebuild Docker images (unless SKIP_BUILD=true)
#   2. Load new images into the existing Kind cluster
#   3. Upgrade the Helm release with latest configuration
#   4. Force rollout restart to pick up the newly loaded images
#
# Usage:
#   ./tests/run_kind_e2e.sh
#
# Environment overrides:
#   CLUSTER_NAME           Kind cluster name (default: geosnap-e2e)
#   NAMESPACE              Kubernetes namespace (default: geosnap-e2e)
#   RELEASE_NAME           Helm release name (default: geosnappro-e2e)
#   KEEP_CLUSTER           Set to "true" to keep cluster after run (default: true)
#   SKIP_BUILD             Set to "true" to skip Docker image builds (default: false)
#   SKIP_TESTS             Set to "true" to skip pytest execution (default: true)
#   KIND_CONFIG            Path to Kind cluster config (default: tests/kind/e2e-kind-config.yaml)
#   IMAGE_TAG              Tag to apply to locally built images (default: kind-e2e)
#   FRONTEND_IMAGE_REPO    Repo for frontend image (default: geosnap/frontend)
#   SCREENSHOT_IMAGE_REPO  Repo for screenshot API image (default: geosnap/screenshot-api)
#   GLUETUN_IMAGE_REPO     Repo for Gluetun API image (default: geosnap/gluetun-api)
#   PYTEST_ARGS            Extra arguments for pytest (default: "-v --tb=short")

set -Eeuo pipefail

# Paths
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-geosnap-e2e}"
NAMESPACE="${NAMESPACE:-geosnap-e2e}"
RELEASE_NAME="${RELEASE_NAME:-geosnappro-e2e}"
KEEP_CLUSTER="${KEEP_CLUSTER:-true}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_TESTS="${SKIP_TESTS:-true}"
KIND_CONFIG="${KIND_CONFIG:-${ROOT_DIR}/tests/kind/e2e-kind-config.yaml}"
IMAGE_TAG="${IMAGE_TAG:-kind-e2e}"
FRONTEND_IMAGE_REPO="${FRONTEND_IMAGE_REPO:-geosnap/frontend}"
SCREENSHOT_IMAGE_REPO="${SCREENSHOT_IMAGE_REPO:-geosnap/screenshot-api}"
GLUETUN_IMAGE_REPO="${GLUETUN_IMAGE_REPO:-geosnap/gluetun-api}"
PYTEST_ARGS="${PYTEST_ARGS:--v --tb=short}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TMP_DIR="$(mktemp -d)"
CLUSTER_CREATED=0
UNIFIED_CHART_PATH="${ROOT_DIR}/deploy/charts/geosnappro"

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*" >&2; }
err()  { echo "[ERROR] $*" >&2; }

cleanup() {
  local exit_code=$?
  if [[ -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
  if [[ "${KEEP_CLUSTER}" != "true" && ${CLUSTER_CREATED} -eq 1 ]]; then
    log "Deleting Kind cluster ${CLUSTER_NAME}"
    if ! kind delete cluster --name "${CLUSTER_NAME}"; then
      warn "Failed to delete Kind cluster ${CLUSTER_NAME}"
    fi
  else
    log "Cluster cleanup skipped (KEEP_CLUSTER=${KEEP_CLUSTER}, CLUSTER_CREATED=${CLUSTER_CREATED})"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT

require_cmd() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    err "Missing required command: ${cmd}. ${hint}"
    exit 1
  fi
}

log "Checking required tooling..."
require_cmd kind "Install Kind: https://kind.sigs.k8s.io/docs/user/quick-start/"
require_cmd kubectl "Install kubectl: https://kubernetes.io/docs/tasks/tools/"
require_cmd helm "Install Helm: https://helm.sh/docs/intro/install/"
require_cmd docker "Install Docker and ensure the daemon is running."
require_cmd "${PYTHON_BIN}" "Install Python or set PYTHON_BIN to a valid interpreter."

log "Ensuring Docker daemon is reachable..."
if ! docker info >/dev/null 2>&1; then
  err "Docker daemon is not reachable. Please start Docker."
  exit 1
fi

ensure_kind_cluster() {
  if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
    log "Re-using existing Kind cluster ${CLUSTER_NAME}"
  else
    log "Creating Kind cluster ${CLUSTER_NAME}"
    kind create cluster --name "${CLUSTER_NAME}" --config "${KIND_CONFIG}"
    CLUSTER_CREATED=1
  fi
  kubectl config use-context "kind-${CLUSTER_NAME}" >/dev/null
}

build_and_load() {
  local image_repo="$1"
  local dockerfile="$2"
  local context_dir="$3"
  local image="${image_repo}:${IMAGE_TAG}"

  log "Building ${image}"
  docker build --pull --tag "${image}" --file "${dockerfile}" "${context_dir}"

  log "Loading ${image} into Kind cluster ${CLUSTER_NAME}"
  kind load docker-image "${image}" --name "${CLUSTER_NAME}"
}

write_unified_values_file() {
  # Note: Using empty SERVERS_JSON to let the API use the bundled servers.json file
  # which contains the full list of 500+ Mullvad servers
  local servers_json=''

  log "Creating unified chart values file for all services"
  cat <<EOF > "${TMP_DIR}/geosnappro-unified-values.yaml"
# Unified GeoSnappro Helm Chart Values
# This single values file configures all three services:
# - Screenshot API
# - Gluetun API
# - Frontend

global:
  imagePullSecrets: []

# Screenshot API Configuration
screenshotApi:
  enabled: true
  replicaCount: 1
  
  image:
    repository: ${SCREENSHOT_IMAGE_REPO}
    tag: ${IMAGE_TAG}
    pullPolicy: IfNotPresent
  
  fullnameOverride: screenshot-api
  
  serviceAccount:
    create: true
  
  service:
    type: ClusterIP
    port: 8000
    targetPort: 8000
  
  env:
    PYTHONUNBUFFERED: "1"
    LOG_LEVEL: INFO
    VPN_SHARED_PROXY_IDLE_TTL_SECONDS: "20"
    API_KEY: ""
    RATE_LIMIT_WINDOW_SECONDS: "60"
    RATE_LIMIT_MAX_REQUESTS: "60"
    CAMOUFOX_EXECUTABLE: ""
    CAMOUFOX_DEFAULT_UA: ""
  
  gluetunApi:
    serviceName: gluetun-api
    port: 8001
  
  resources: {}
  
  livenessProbe:
    enabled: true
    httpGet:
      path: /health
      port: http
    initialDelaySeconds: 30
    periodSeconds: 10
    timeoutSeconds: 5
    failureThreshold: 3
  
  readinessProbe:
    enabled: true
    httpGet:
      path: /health
      port: http
    initialDelaySeconds: 10
    periodSeconds: 5
    timeoutSeconds: 3
    failureThreshold: 3
  
  startupProbe:
    enabled: false

# Gluetun API Configuration
gluetunApi:
  enabled: true
  replicaCount: 1
  
  image:
    repository: ${GLUETUN_IMAGE_REPO}
    tag: ${IMAGE_TAG}
    pullPolicy: IfNotPresent
  
  fullnameOverride: gluetun-api
  
  serviceAccount:
    create: true
  
  rbac:
    create: true
  
  config:
    namespace: ${NAMESPACE}
    instanceLimit: 1
    logLevel: INFO
    pythonUnbuffered: "1"
    serversFilePath: ""
    serversJSON: |
      ${servers_json}
    firewallInputPorts: "8888"
  
  wireguardSecret:
    name: gluetun-wireguard-credentials
    privateKeyKey: wireguard-private-key
    addressesKey: wireguard-addresses
  
  # Dummy WireGuard credentials for testing
  # The unified chart will create the secret automatically
  wireguard:
    privateKey: "aCv31OvwOxhL7SzeSIAiQm1nXPw/pPNi+HPMj9rcxG8="
    addresses: "10.68.50.98/32"
  
  service:
    type: ClusterIP
    port: 8001
  
  resources: {}

# Frontend Configuration
frontend:
  enabled: true
  replicaCount: 1
  
  image:
    repository: ${FRONTEND_IMAGE_REPO}
    tag: ${IMAGE_TAG}
    pullPolicy: IfNotPresent
  
  fullnameOverride: frontend
  
  serviceAccount:
    create: true
  
  service:
    type: ClusterIP
    port: 5000
    targetPort: 5000
  
  env:
    BACKEND_URL: http://screenshot-api:8000
    BACKEND_WS_PUBLIC_URL: ws://localhost:5000
    GLUETUN_API_URL: http://gluetun-api:8001
    DEBUG: "false"
    PORT: "5000"
    POLL_INTERVAL_SECONDS: "2"
    MEDIA_DIR: /app/media
  
  mediaVolume:
    enabled: false
  
  resources: {}
  
  autoscaling:
    enabled: false
EOF
}

create_namespace() {
  if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    log "Creating namespace ${NAMESPACE}"
    kubectl create namespace "${NAMESPACE}"
  else
    log "Namespace ${NAMESPACE} already exists"
  fi
}

ensure_wireguard_secret_removed() {
  log "Removing any existing WireGuard credentials secret (Helm will create it)"
  if kubectl get secret gluetun-wireguard-credentials -n "${NAMESPACE}" >/dev/null 2>&1; then
    log "Deleting existing secret to allow Helm to manage it"
    kubectl delete secret gluetun-wireguard-credentials -n "${NAMESPACE}" 2>/dev/null || true
  fi
}

check_release_exists() {
  if helm list -n "${NAMESPACE}" | grep -q "^${RELEASE_NAME}"; then
    return 0
  else
    return 1
  fi
}

rollout_restart_deployments() {
  log "Rolling out updated images to existing deployments"
  
  # Get all deployments from the release
  local deployments=$(kubectl get deployments -n "${NAMESPACE}" \
    -l "app.kubernetes.io/instance=${RELEASE_NAME}" \
    -o jsonpath='{.items[*].metadata.name}')
  
  if [ -z "$deployments" ]; then
    warn "No deployments found for release ${RELEASE_NAME}"
    return
  fi
  
  for deployment in $deployments; do
    log "Restarting deployment: ${deployment}"
    kubectl rollout restart deployment "${deployment}" -n "${NAMESPACE}"
  done
  
  log "Waiting for rollout to complete..."
  for deployment in $deployments; do
    log "Waiting for ${deployment}..."
    kubectl rollout status deployment "${deployment}" -n "${NAMESPACE}" --timeout=5m
  done
  
  log "All deployments rolled out successfully!"
}

deploy_unified_chart() {
  log "Deploying UNIFIED GeoSnappro Helm chart"
  log "Chart location: ${UNIFIED_CHART_PATH}"
  log "Release name: ${RELEASE_NAME}"
  log "This will deploy: screenshot-api, gluetun-api, and frontend (all in one chart)"
  
  if [ ! -d "${UNIFIED_CHART_PATH}" ]; then
    err "Unified chart not found at ${UNIFIED_CHART_PATH}"
    err "Expected chart structure: deploy/charts/geosnappro/"
    exit 1
  fi
  
  local is_upgrade=false
  if check_release_exists; then
    log "Release ${RELEASE_NAME} already exists - performing upgrade"
    is_upgrade=true
  else
    log "Release ${RELEASE_NAME} does not exist - performing fresh install"
  fi
  
  helm upgrade --install "${RELEASE_NAME}" "${UNIFIED_CHART_PATH}" \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --values "${TMP_DIR}/geosnappro-unified-values.yaml" \
    --wait \
    --timeout 15m

  log "Waiting for all deployments from unified chart to become available"
  kubectl wait --namespace "${NAMESPACE}" \
    --for=condition=Available \
    --selector="app.kubernetes.io/instance=${RELEASE_NAME}" \
    --timeout=900s \
    deployment --all
  
  log "Unified chart deployment complete!"
  log "Services deployed:"
  kubectl get svc -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE_NAME}"
  log "Deployments:"
  kubectl get deploy -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE_NAME}"
  
  if [ "$is_upgrade" = true ]; then
    log "Note: Helm upgrade completed. To force pull new images, use rollout restart."
  fi
}

install_python_dependencies() {
  log "Installing Python test dependencies"
  "${PYTHON_BIN}" -m pip install --upgrade pip >/dev/null
  "${PYTHON_BIN}" -m pip install --requirement "${ROOT_DIR}/tests/requirements.txt"
}

run_pytests() {
  log "Running pytest end-to-end checks against unified chart deployment"
  export E2E_NAMESPACE="${NAMESPACE}"
  export E2E_RELEASE_NAME="${RELEASE_NAME}"
  export E2E_CHART_PATH="${UNIFIED_CHART_PATH}"
  export KIND_CLUSTER_NAME="${CLUSTER_NAME}"
  export PATH="${ROOT_DIR}/tests:${PATH}"

  log "Test environment:"
  log "  E2E_NAMESPACE=${E2E_NAMESPACE}"
  log "  E2E_RELEASE_NAME=${E2E_RELEASE_NAME}"
  log "  E2E_CHART_PATH=${E2E_CHART_PATH}"
  log "  KIND_CLUSTER_NAME=${KIND_CLUSTER_NAME}"

  pushd "${ROOT_DIR}" >/dev/null
  "${PYTHON_BIN}" -m pytest tests/test_kind_e2e.py ${PYTEST_ARGS}
  popd >/dev/null
}

main() {
  log "=========================================="
  log "GeoSnappro Unified Chart E2E Test Runner"
  log "=========================================="
  log "Cluster: ${CLUSTER_NAME}"
  log "Namespace: ${NAMESPACE}"
  log "Release: ${RELEASE_NAME}"
  log "Chart: ${UNIFIED_CHART_PATH}"
  log "=========================================="
  
  ensure_kind_cluster
  
  local release_exists=false
  if check_release_exists; then
    log "=========================================="
    log "⚙️  EXISTING DEPLOYMENT DETECTED"
    log "=========================================="
    log "Release '${RELEASE_NAME}' already exists in namespace '${NAMESPACE}'"
    log "The script will:"
    log "  1. Rebuild Docker images (frontend, screenshot-api, gluetun-api)"
    log "  2. Load updated images into Kind cluster"
    log "  3. Upgrade Helm release with latest configuration"
    log "  4. Force rollout restart to apply new images"
    log "=========================================="
    release_exists=true
  fi

  if [[ "${SKIP_BUILD}" != "true" ]]; then
    log "Building and loading Docker images into Kind cluster..."
    build_and_load "${GLUETUN_IMAGE_REPO}" "${ROOT_DIR}/services/gluetun-api-k8s/Dockerfile" "${ROOT_DIR}/services/gluetun-api-k8s"
    build_and_load "${SCREENSHOT_IMAGE_REPO}" "${ROOT_DIR}/services/screenshot-api/Dockerfile" "${ROOT_DIR}/services/screenshot-api"
    build_and_load "${FRONTEND_IMAGE_REPO}" "${ROOT_DIR}/services/frontend/Dockerfile" "${ROOT_DIR}/services/frontend"
    log "✅ All images built and loaded successfully"
  else
    log "Skipping Docker image build (SKIP_BUILD=true)"
  fi

  write_unified_values_file
  create_namespace
  
  # Only remove secret if doing fresh install
  if [ "$release_exists" = false ]; then
    ensure_wireguard_secret_removed
  fi
  
  deploy_unified_chart
  
  # If release existed and we rebuilt images, force rollout restart after helm upgrade
  # This ensures pods pick up the newly loaded images with the same tag
  if [ "$release_exists" = true ] && [[ "${SKIP_BUILD}" != "true" ]]; then
    log "=========================================="
    log "🔄 ROLLING OUT NEW IMAGES"
    log "=========================================="
    log "Forcing rollout restart to pick up newly built images..."
    rollout_restart_deployments
    log "=========================================="
    log "✅ All pods updated with new images!"
    log "=========================================="
  fi

  if [[ "${SKIP_TESTS}" != "true" ]]; then
    install_python_dependencies
    run_pytests
    log "=========================================="
    log "✅ All tests completed successfully!"
    log "=========================================="
  else
    log "Skipping pytest execution (SKIP_TESTS=true)"
    log "=========================================="
    log "Cluster '${CLUSTER_NAME}' in namespace '${NAMESPACE}' is ready for manual validation."
    log ""
    log "Access frontend at: kubectl port-forward svc/frontend 5000:5000 -n ${NAMESPACE}"
    log "Then visit: http://localhost:5000"
    log ""
    log "Remember to delete the cluster manually with:"
    log "  kind delete cluster --name ${CLUSTER_NAME}"
    log "=========================================="
  fi

  log "Kind deployment workflow completed"
}

main "$@"


