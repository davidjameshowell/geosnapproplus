#!/bin/bash
# Run pytest tests using kubectl port-forward

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
NAMESPACE="gluetun-system"
LOCAL_PORT=8001

echo "🧪 Running Gluetun K8s API tests with port-forward..."
echo ""

# Start port-forward in background
echo "🔌 Starting port-forward to gluetun-k8s-api:8001 -> localhost:$LOCAL_PORT..."
kubectl port-forward -n "$NAMESPACE" svc/gluetun-k8s-api "$LOCAL_PORT:8001" > /dev/null 2>&1 &
PORT_FORWARD_PID=$!

# Function to cleanup port-forward on exit
cleanup() {
    echo ""
    echo "🧹 Stopping port-forward..."
    kill $PORT_FORWARD_PID 2>/dev/null || true
    wait $PORT_FORWARD_PID 2>/dev/null || true
}

trap cleanup EXIT INT TERM

# Wait for port-forward to be ready
echo "⏳ Waiting for port-forward to be ready..."
for i in {1..10}; do
    if curl -s http://localhost:$LOCAL_PORT/health > /dev/null 2>&1; then
        echo "✅ Port-forward ready!"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ Port-forward failed to become ready"
        exit 1
    fi
    sleep 1
done

# Run tests
echo ""
echo "🧪 Running tests..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$PROJECT_ROOT"
GLUETUN_K8S_API_URL="http://localhost:$LOCAL_PORT" pytest tests/test_gluetun_k8s_api.py -v "${@}"
TEST_EXIT_CODE=$?

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Tests passed!"
    exit 0
else
    echo "❌ Tests failed!"
    exit $TEST_EXIT_CODE
fi

