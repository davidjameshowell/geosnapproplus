#!/bin/bash

# Script to run frontend tests in a Kubernetes environment
# This script deploys the frontend using the Helm chart and runs tests against it

set -e

# Configuration
NAMESPACE=${NAMESPACE:-"default"}
RELEASE_NAME=${RELEASE_NAME:-"frontend-test"}
CHART_PATH=${CHART_PATH:-"./charts/frontend"}
TEST_TIMEOUT=${TEST_TIMEOUT:-"300s"}
CLEANUP=${CLEANUP:-"true"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if we can connect to the cluster
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    print_status "kubectl is available and connected to the cluster"
}

# Function to check if helm is available
check_helm() {
    if ! command -v helm &> /dev/null; then
        print_error "helm is not installed or not in PATH"
        exit 1
    fi
    
    print_status "helm is available"
}

# Function to deploy the frontend using Helm
deploy_frontend() {
    print_status "Deploying frontend with Helm chart..."
    
    # Create namespace if it doesn't exist
    if ! kubectl get namespace ${NAMESPACE} &> /dev/null; then
        print_status "Creating namespace: ${NAMESPACE}"
        kubectl create namespace ${NAMESPACE}
    fi
    
    # Deploy the frontend
    helm upgrade --install ${RELEASE_NAME} ${CHART_PATH} \
        --namespace ${NAMESPACE} \
        --set image.tag="latest" \
        --set ingress.enabled=true \
        --set ingress.className="nginx" \
        --set service.type="NodePort" \
        --wait \
        --timeout=${TEST_TIMEOUT}
    
    print_status "Frontend deployed successfully"
}

# Function to get the frontend URL
get_frontend_url() {
    # Get the service details
    SERVICE_NAME=$(helm get values ${RELEASE_NAME} -n ${NAMESPACE} -o json | jq -r '.fullnameOverride // "frontend"')
    
    # Check if we're using a local cluster (like Docker Desktop or Minikube)
    if kubectl config current-context | grep -q -E "(docker-desktop|minikube|kind)"; then
        # For local clusters, use NodePort
        NODE_PORT=$(kubectl get service ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.ports[0].nodePort}')
        NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
        
        if [ -z "$NODE_IP" ]; then
            NODE_IP="localhost"
        fi
        
        FRONTEND_URL="http://${NODE_IP}:${NODE_PORT}"
    else
        # For cloud clusters, use LoadBalancer or Ingress
        if kubectl get service ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.type}' | grep -q "LoadBalancer"; then
            # Wait for LoadBalancer IP
            print_status "Waiting for LoadBalancer IP..."
            LB_IP=""
            for i in {1..30}; do
                LB_IP=$(kubectl get service ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
                if [ -n "$LB_IP" ]; then
                    break
                fi
                sleep 10
            done
            
            if [ -z "$LB_IP" ]; then
                print_error "Could not get LoadBalancer IP"
                exit 1
            fi
            
            FRONTEND_URL="http://${LB_IP}:5000"
        elif kubectl get ingress ${SERVICE_NAME} -n ${NAMESPACE} &> /dev/null; then
            # Use Ingress
            INGRESS_HOST=$(kubectl get ingress ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.rules[0].host}')
            FRONTEND_URL="http://${INGRESS_HOST}"
        else
            print_error "Neither LoadBalancer nor Ingress is configured"
            exit 1
        fi
    fi
    
    print_status "Frontend URL: ${FRONTEND_URL}"
    echo ${FRONTEND_URL}
}

# Function to get the backend URL
get_backend_url() {
    # Get the backend service name (assuming it's deployed as 'screenshot-api')
    BACKEND_SERVICE="screenshot-api"
    
    # Check if we're using a local cluster
    if kubectl config current-context | grep -q -E "(docker-desktop|minikube|kind)"; then
        # For local clusters, use NodePort
        NODE_PORT=$(kubectl get service ${BACKEND_SERVICE} -n ${NAMESPACE} -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "")
        
        if [ -n "$NODE_PORT" ]; then
            NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
            if [ -z "$NODE_IP" ]; then
                NODE_IP="localhost"
            fi
            BACKEND_URL="http://${NODE_IP}:${NODE_PORT}"
        else
            # Fallback to service name (for tests running inside the cluster)
            BACKEND_URL="http://${BACKEND_SERVICE}:8000"
        fi
    else
        # For cloud clusters or tests running inside the cluster
        BACKEND_URL="http://${BACKEND_SERVICE}:8000"
    fi
    
    print_status "Backend URL: ${BACKEND_URL}"
    echo ${BACKEND_URL}
}

# Function to get the gluetun API URL
get_gluetun_api_url() {
    # Get the gluetun API service name
    GLUETUN_SERVICE="gluetun-api"
    
    # For tests running inside the cluster
    GLUETUN_API_URL="http://${GLUETUN_SERVICE}:8001"
    
    print_status "Gluetun API URL: ${GLUETUN_API_URL}"
    echo ${GLUETUN_API_URL}
}

# Function to run the tests
run_tests() {
    print_status "Running frontend tests..."
    
    # Get URLs
    FRONTEND_URL=$(get_frontend_url)
    BACKEND_URL=$(get_backend_url)
    GLUETUN_API_URL=$(get_gluetun_api_url)
    
    # Wait for the frontend to be ready
    print_status "Waiting for frontend to be ready..."
    for i in {1..30}; do
        if curl -s -f ${FRONTEND_URL} > /dev/null; then
            print_status "Frontend is ready"
            break
        fi
        
        if [ $i -eq 30 ]; then
            print_error "Frontend did not become ready in time"
            exit 1
        fi
        
        sleep 10
    done
    
    # Run the tests
    cd $(dirname $0)
    
    # Set environment variables for the tests
    export FRONTEND_URL=${FRONTEND_URL}
    export BACKEND_URL=${BACKEND_URL}
    export GLUETUN_API_URL=${GLUETUN_API_URL}
    
    # Run pytest
    python -m pytest test_frontend.py -v --tb=short
    
    print_status "Tests completed"
}

# Function to cleanup
cleanup() {
    if [ "$CLEANUP" = "true" ]; then
        print_status "Cleaning up..."
        helm uninstall ${RELEASE_NAME} -n ${NAMESPACE} || true
        print_status "Cleanup completed"
    else
        print_warning "Skipping cleanup (CLEANUP=false)"
    fi
}

# Main script
main() {
    print_status "Starting frontend tests in Kubernetes..."
    
    # Check prerequisites
    check_kubectl
    check_helm
    
    # Deploy the frontend
    deploy_frontend
    
    # Run the tests
    run_tests
    
    # Cleanup
    cleanup
    
    print_status "All tests completed successfully!"
}

# Handle script interruption
trap cleanup EXIT

# Run the main function
main "$@"
