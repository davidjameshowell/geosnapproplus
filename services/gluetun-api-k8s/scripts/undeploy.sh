#!/bin/bash
# Remove Gluetun K8s API from Kubernetes cluster

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR/../k8s"

echo "Removing Gluetun K8s API from Kubernetes..."

echo "Deleting services..."
kubectl delete -f "$K8S_DIR/06-nodeport-service.yaml" --ignore-not-found=true
kubectl delete -f "$K8S_DIR/05-service.yaml" --ignore-not-found=true

echo "Deleting deployment..."
kubectl delete -f "$K8S_DIR/04-deployment.yaml" --ignore-not-found=true

echo "Deleting ConfigMap..."
kubectl delete -f "$K8S_DIR/03-configmap.yaml" --ignore-not-found=true

echo "Deleting RBAC configuration..."
kubectl delete -f "$K8S_DIR/02-rbac.yaml" --ignore-not-found=true

echo "Cleaning up any running Gluetun pods..."
kubectl delete pods -n gluetun-system -l managed-by=gluetun-k8s-api --ignore-not-found=true

echo ""
echo "To also delete the namespace and secrets:"
echo "  kubectl delete namespace gluetun-system"
echo ""
echo "Undeployment complete!"

