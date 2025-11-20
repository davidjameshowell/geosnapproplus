#!/bin/bash
# Run pytest tests inside the Kubernetes cluster

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
NAMESPACE="gluetun-system"
POD_NAME="gluetun-test-runner-$$"

echo "🧪 Running Gluetun K8s API tests inside cluster..."
echo ""

# Ensure namespace exists
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
  echo "📁 Namespace '$NAMESPACE' does not exist; creating..."
  kubectl create namespace "$NAMESPACE"
fi

# Ensure WireGuard credentials secret matches repo values
echo "🔐 Applying WireGuard credentials from k8s/01-secret.yaml..."
kubectl apply -f "$PROJECT_ROOT/k8s/01-secret.yaml"

# Create temporary test runner pod
echo "📦 Creating test runner pod..."
kubectl run "$POD_NAME" \
  --image=python:3.11-slim \
  --restart=Never \
  --namespace="$NAMESPACE" \
  --env="GLUETUN_K8S_API_URL=http://gluetun-k8s-api:8001" \
  --command -- sleep 300

# Wait for pod to be ready
echo "⏳ Waiting for pod to be ready..."
kubectl wait --for=condition=Ready \
  "pod/$POD_NAME" \
  --namespace="$NAMESPACE" \
  --timeout=60s

# Copy test files
echo "📋 Copying test files..."
kubectl cp "$PROJECT_ROOT/tests/" \
  "$NAMESPACE/$POD_NAME:/tmp/tests/" \
  --container="$POD_NAME"

kubectl cp "$PROJECT_ROOT/requirements.txt" \
  "$NAMESPACE/$POD_NAME:/tmp/requirements.txt" \
  --container="$POD_NAME"

# Install dependencies
echo "📦 Installing dependencies..."
kubectl exec "$POD_NAME" \
  --namespace="$NAMESPACE" \
  -- bash -c "pip install -q pytest requests"

# Run tests
echo ""
echo "🧪 Running tests..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl exec "$POD_NAME" \
  --namespace="$NAMESPACE" \
  -- pytest /tmp/tests/test_gluetun_k8s_api.py -v "${@}"

TEST_EXIT_CODE=$?

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Cleanup
echo "🧹 Cleaning up..."
kubectl delete pod "$POD_NAME" --namespace="$NAMESPACE" --ignore-not-found=true

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Tests passed!"
    exit 0
else
    echo "❌ Tests failed!"
    exit $TEST_EXIT_CODE
fi
