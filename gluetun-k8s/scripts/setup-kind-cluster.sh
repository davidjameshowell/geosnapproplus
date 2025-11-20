#!/bin/bash
# Create a kind cluster for testing Gluetun K8s API

set -e

CLUSTER_NAME="${KIND_CLUSTER_NAME:-gluetun-test}"

echo "Creating kind cluster: $CLUSTER_NAME"

# Check if cluster already exists
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '$CLUSTER_NAME' already exists"
    echo "To delete and recreate, run: kind delete cluster --name $CLUSTER_NAME"
    exit 0
fi

# Create cluster with extra configuration
cat <<EOF | kind create cluster --name "$CLUSTER_NAME" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30801
        hostPort: 30801
        protocol: TCP
EOF

echo ""
echo "Kind cluster '$CLUSTER_NAME' created successfully!"
echo ""
echo "To use this cluster:"
echo "  kubectl cluster-info --context kind-$CLUSTER_NAME"
echo ""
echo "To delete this cluster when done:"
echo "  kind delete cluster --name $CLUSTER_NAME"
echo ""

