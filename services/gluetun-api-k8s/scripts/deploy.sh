#!/bin/bash
# Deploy Gluetun K8s API to Kubernetes cluster

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR/../k8s"

echo "Deploying Gluetun K8s API to Kubernetes..."

# Check if WireGuard credentials are set
if [ -z "$WIREGUARD_PRIVATE_KEY" ] || [ -z "$WIREGUARD_ADDRESSES" ]; then
    echo "ERROR: WIREGUARD_PRIVATE_KEY and WIREGUARD_ADDRESSES environment variables must be set"
    echo "Example:"
    echo "  export WIREGUARD_PRIVATE_KEY='your-private-key'"
    echo "  export WIREGUARD_ADDRESSES='10.x.x.x/32'"
    echo "  ./scripts/deploy.sh"
    exit 1
fi

echo "Creating namespace..."
kubectl apply -f "$K8S_DIR/00-namespace.yaml"

echo "Creating secret with WireGuard credentials..."
kubectl create secret generic gluetun-wireguard-credentials \
    --from-literal=wireguard-private-key="$WIREGUARD_PRIVATE_KEY" \
    --from-literal=wireguard-addresses="$WIREGUARD_ADDRESSES" \
    -n gluetun-system \
    --dry-run=client -o yaml | kubectl apply -f -

echo "Applying RBAC configuration..."
kubectl apply -f "$K8S_DIR/02-rbac.yaml"

echo "Applying ConfigMap..."
kubectl apply -f "$K8S_DIR/03-configmap.yaml"

echo "Deploying API server..."
kubectl apply -f "$K8S_DIR/04-deployment.yaml"

echo "Creating services..."
kubectl apply -f "$K8S_DIR/05-service.yaml"
kubectl apply -f "$K8S_DIR/06-nodeport-service.yaml"

echo ""
echo "Deployment complete!"
echo ""
echo "To check the deployment status:"
echo "  kubectl get pods -n gluetun-system"
echo ""
echo "To view logs:"
echo "  kubectl logs -n gluetun-system -l app=gluetun-k8s-api -f"
echo ""
echo "API will be accessible at: http://localhost:30801"
echo ""

