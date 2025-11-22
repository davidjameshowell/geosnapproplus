#!/bin/bash
# Build the gluetun-k8s image, ensure a kind cluster exists, load the image,
# apply Mullvad credentials, and deploy the Helm chart.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_ROOT")"
CHART_PATH="$REPO_ROOT/charts/gluetun-api"

CLUSTER_NAME="${KIND_CLUSTER_NAME:-gluetun-test}"
IMAGE_REPO="${IMAGE_NAME:-gluetun-k8s-api}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
HELM_RELEASE="${HELM_RELEASE_NAME:-gluetun-api}"
NAMESPACE="${NAMESPACE:-gluetun-system}"

SERVERS_JSON_PATH="$PROJECT_ROOT/data/servers.json"

if [[ -n "${WIREGUARD_PRIVATE_KEY:-}" && -n "${WIREGUARD_ADDRESSES:-}" ]]; then
  echo "🗂️  Exporting Mullvad server list for bundling..."
  "$SCRIPT_DIR/export-servers-json.sh" "$SERVERS_JSON_PATH"
else
  echo "ℹ️  WIREGUARD_PRIVATE_KEY / WIREGUARD_ADDRESSES not set; using existing bundled servers.json"
fi

echo "🛠️  Building Docker image ${IMAGE_REPO}:${IMAGE_TAG}..."
docker build -t "${IMAGE_REPO}:${IMAGE_TAG}" "$PROJECT_ROOT"

if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "🌱 kind cluster '${CLUSTER_NAME}' not found. Creating..."
  cat <<EOF | kind create cluster --name "${CLUSTER_NAME}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30801
        hostPort: 30801
        protocol: TCP
EOF
else
  echo "✅ kind cluster '${CLUSTER_NAME}' already exists."
fi

echo "🔁 Setting kubectl context to kind-${CLUSTER_NAME}..."
kubectl config use-context "kind-${CLUSTER_NAME}" >/dev/null

if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "📁 Namespace '${NAMESPACE}' not found. Creating..."
  kubectl create namespace "${NAMESPACE}"
else
  echo "✅ Namespace '${NAMESPACE}' already exists."
fi

echo "📦 Loading image into kind cluster..."
kind load docker-image --name "${CLUSTER_NAME}" "${IMAGE_REPO}:${IMAGE_TAG}"

if [[ -n "${WIREGUARD_PRIVATE_KEY:-}" && -n "${WIREGUARD_ADDRESSES:-}" ]]; then
  echo "🔐 Creating WireGuard secret '${NAMESPACE}/gluetun-wireguard-credentials' from environment variables..."
  kubectl create secret generic gluetun-wireguard-credentials \
    --namespace "${NAMESPACE}" \
    --from-literal=wireguard-private-key="${WIREGUARD_PRIVATE_KEY}" \
    --from-literal=wireguard-addresses="${WIREGUARD_ADDRESSES}" \
    --dry-run=client -o yaml | kubectl apply -f -
else
  echo "🔐 WIREGUARD_PRIVATE_KEY / WIREGUARD_ADDRESSES not set. Applying default secret from k8s/01-secret.yaml..."
  kubectl apply -f "$PROJECT_ROOT/k8s/01-secret.yaml"
fi

echo "🚀 Deploying Helm release '${HELM_RELEASE}' into namespace '${NAMESPACE}'..."
helm upgrade --install "${HELM_RELEASE}" "${CHART_PATH}" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --set image.repository="${IMAGE_REPO}" \
  --set image.tag="${IMAGE_TAG}"

echo ""
echo "✅ Deployment initiated."
echo "ℹ️  Run the following commands to inspect the deployment:"
echo "    kubectl get pods -n ${NAMESPACE}"
echo "    kubectl get svc -n ${NAMESPACE}"
echo "    helm status ${HELM_RELEASE} -n ${NAMESPACE}"

