#!/bin/bash

# Script to run frontend tests in a Kubernetes environment
# This script manages a Kind cluster, deploys the frontend Helm chart, and
# executes the integration test suite.
#
# Usage:
#   ./run_k8s_tests.sh [OPTIONS]
#
# Options:
#   --use-existing-cluster     Use an existing Kind cluster (error if missing)
#   --cluster-name <name>      Override the Kind cluster name (default: frontend-kind)
#   --skip-build               Skip Docker image build step (image must exist locally)
#   --skip-load                Skip loading the Docker image into Kind
#   --cleanup-only             Only remove the Helm release (no tests)
#   --destroy-cluster          Delete the Kind cluster after the run
#   --no-cleanup               Leave the Helm release deployed after the run
#   --help                     Show this help message
#
# Examples:
#   ./run_k8s_tests.sh                           # Create Kind cluster, build image, run tests
#   ./run_k8s_tests.sh --cluster-name ci-run     # Use a custom cluster name
#   ./run_k8s_tests.sh --use-existing-cluster    # Reuse a running cluster for faster tests

set -euo pipefail

# -----------------------------------------------------------------------------
# Default configuration (can be overridden via env vars or CLI flags)
# -----------------------------------------------------------------------------
NAMESPACE=${NAMESPACE:-"default"}
RELEASE_NAME=${RELEASE_NAME:-"frontend-test"}
CHART_PATH=${CHART_PATH:-"../../charts/frontend"}
TEST_TIMEOUT=${TEST_TIMEOUT:-"300s"}
CLEANUP=${CLEANUP:-"true"}
USE_EXISTING_CLUSTER=${USE_EXISTING_CLUSTER:-"false"}
SKIP_BUILD=${SKIP_BUILD:-"false"}
SKIP_LOAD=${SKIP_LOAD:-"false"}
CLEANUP_ONLY=${CLEANUP_ONLY:-"false"}
DESTROY_CLUSTER=${DESTROY_CLUSTER:-"false"}
CLUSTER_NAME=${CLUSTER_NAME:-"frontend-kind"}
IMAGE_NAME=${IMAGE_NAME:-"geosnappro-frontend"}
IMAGE_TAG=${IMAGE_TAG:-"test"}
KUBECONFIG_DIR=${KUBECONFIG_DIR:-"$HOME/.kube"}
KUBECONFIG_PATH=""
CLUSTER_CREATED="false"
KUBECONFIG_AVAILABLE="false"
CLEANUP_PERFORMED="false"

# -----------------------------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
    sed -n '1,35p' "$0"
}

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --use-existing-cluster)
                USE_EXISTING_CLUSTER="true"
                shift
                ;;
            --cluster-name)
                [[ $# -lt 2 ]] && { print_error "--cluster-name requires a value"; exit 1; }
                CLUSTER_NAME="$2"
                shift 2
                ;;
            --skip-build)
                SKIP_BUILD="true"
                shift
                ;;
            --skip-load)
                SKIP_LOAD="true"
                shift
                ;;
            --cleanup-only)
                CLEANUP_ONLY="true"
                shift
                ;;
            --destroy-cluster)
                DESTROY_CLUSTER="true"
                shift
                ;;
            --no-cleanup)
                CLEANUP="false"
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

# -----------------------------------------------------------------------------
# Environment checks
# -----------------------------------------------------------------------------
ensure_binary() {
    local bin="$1"
    local message="$2"
    if ! command -v "$bin" &>/dev/null; then
        print_error "$message"
        exit 1
    fi
}

ensure_kind_cluster() {
    ensure_binary kind "kind CLI is required. Install from https://kind.sigs.k8s.io/."
    mkdir -p "$KUBECONFIG_DIR"

    if kind get clusters | grep -qw "$CLUSTER_NAME"; then
        print_status "Using existing Kind cluster '$CLUSTER_NAME'"
        kind get kubeconfig --name "$CLUSTER_NAME" > "$KUBECONFIG_PATH"
    else
        if [[ "$USE_EXISTING_CLUSTER" == "true" ]]; then
            print_error "Requested to reuse Kind cluster '$CLUSTER_NAME', but it does not exist."
            exit 1
        fi
        print_status "Creating Kind cluster '$CLUSTER_NAME'..."
        kind create cluster --name "$CLUSTER_NAME" --wait 300s
        kind get kubeconfig --name "$CLUSTER_NAME" > "$KUBECONFIG_PATH"
        CLUSTER_CREATED="true"
    fi

    chmod 600 "$KUBECONFIG_PATH"
    export KUBECONFIG="$KUBECONFIG_PATH"
    kubectl config use-context "kind-$CLUSTER_NAME" >/dev/null 2>&1 || true
    KUBECONFIG_AVAILABLE="true"
}

check_kubectl() {
    ensure_binary kubectl "kubectl is required. Install from https://kubernetes.io/docs/tasks/tools/."

    if ! kubectl cluster-info &>/dev/null; then
        print_error "kubectl cannot reach the cluster using KUBECONFIG=$KUBECONFIG_PATH"
        exit 1
    fi
    print_status "kubectl is available and connected"
}

check_helm() { ensure_binary helm "helm is required. Install from https://helm.sh/."; print_status "helm is available"; }
check_docker() { ensure_binary docker "Docker is required for building/loading images."; print_status "Docker is available"; }

# -----------------------------------------------------------------------------
# Build & deploy helpers
# -----------------------------------------------------------------------------
build_and_load_image() {
    if [[ "$SKIP_BUILD" == "true" ]]; then
        print_status "Skipping Docker image build"
    else
        print_status "Building Docker image ${IMAGE_NAME}:${IMAGE_TAG}..."
        pushd ../../frontend >/dev/null
        docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f Dockerfile .
        popd >/dev/null
    fi

    if [[ "$SKIP_LOAD" == "true" ]]; then
        print_status "Skipping Kind image load"
    else
        print_status "Loading image into Kind (cluster: $CLUSTER_NAME)..."
        kind load docker-image --name "$CLUSTER_NAME" "${IMAGE_NAME}:${IMAGE_TAG}"
    fi

    print_status "Docker image ready for deployment"
}

deploy_frontend() {
    print_status "Deploying Helm release '${RELEASE_NAME}'..."

    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        print_status "Creating namespace '$NAMESPACE'"
        kubectl create namespace "$NAMESPACE"
    fi

    helm upgrade --install "$RELEASE_NAME" "$CHART_PATH" \
        --namespace "$NAMESPACE" \
        --set image.repository="$IMAGE_NAME" \
        --set image.tag="$IMAGE_TAG" \
        --set ingress.enabled=false \
        --set service.type="NodePort" \
        --wait \
        --timeout="$TEST_TIMEOUT"

    print_status "Helm release deployed"
}

# -----------------------------------------------------------------------------
# URL helpers
# -----------------------------------------------------------------------------
resolve_service_name() {
    local selector="$1"
    kubectl get svc -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
}

get_frontend_url() {
    local selector="app.kubernetes.io/instance=${RELEASE_NAME},app.kubernetes.io/name=frontend"
    local service_name
    service_name=$(resolve_service_name "$selector")

    if [[ -z "$service_name" ]]; then
        selector="app.kubernetes.io/instance=${RELEASE_NAME}"
        service_name=$(resolve_service_name "$selector")
    fi

    if [[ -z "$service_name" ]]; then
        print_error "Unable to determine frontend service name"
        exit 1
    fi

    local node_port
    node_port=$(kubectl get svc "$service_name" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}')
    local node_ip
    node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

    if [[ -z "$node_ip" ]]; then
        node_ip="localhost"
    fi

    FRONTEND_URL="http://${node_ip}:${node_port}"
    print_status "Resolved frontend URL: $FRONTEND_URL"
}

get_backend_url() {
    local service_name="screenshot-api"
    if kubectl get svc "$service_name" -n "$NAMESPACE" &>/dev/null; then
        local node_port
        node_port=$(kubectl get svc "$service_name" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}')
        local node_ip
        node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
        if [[ -z "$node_ip" ]]; then
            node_ip="localhost"
        fi
        BACKEND_URL="http://${node_ip}:${node_port}"
    else
        print_warning "Backend service '$service_name' not found in namespace '$NAMESPACE'; defaulting to localhost:8000"
        BACKEND_URL="http://localhost:8000"
    fi
    print_status "Backend URL: $BACKEND_URL"
}

get_gluetun_url() {
    local service_name="gluetun-api"
    if kubectl get svc "$service_name" -n "$NAMESPACE" &>/dev/null; then
        local node_port
        node_port=$(kubectl get svc "$service_name" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}')
        local node_ip
        node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
        if [[ -z "$node_ip" ]]; then
            node_ip="localhost"
        fi
        GLUETUN_API_URL="http://${node_ip}:${node_port}"
    else
        print_warning "Gluetun API service '$service_name' not found in namespace '$NAMESPACE'; defaulting to localhost:8001"
        GLUETUN_API_URL="http://localhost:8001"
    fi
    print_status "Gluetun API URL: $GLUETUN_API_URL"
}

# -----------------------------------------------------------------------------
# Test execution
# -----------------------------------------------------------------------------
run_tests() {
    print_status "Waiting for frontend service to become ready..."
    for _ in {1..30}; do
        if curl -sf "$FRONTEND_URL" >/dev/null 2>&1; then
            print_status "Frontend is responding"
            break
        fi
        sleep 5
    done

    print_status "Running pytest suite..."
    pushd "$(dirname "$0")" >/dev/null
    FRONTEND_URL="$FRONTEND_URL" \
    BACKEND_URL="$BACKEND_URL" \
    GLUETUN_API_URL="$GLUETUN_API_URL" \
        python -m pytest test_frontend.py -v --tb=short
    popd >/dev/null
}

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
cleanup() {
    if [[ "$CLEANUP_PERFORMED" == "true" ]]; then
        return
    fi
    CLEANUP_PERFORMED="true"

    if [[ "$KUBECONFIG_AVAILABLE" == "true" && "$CLEANUP" == "true" ]]; then
        print_status "Uninstalling Helm release '${RELEASE_NAME}'..."
        helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" >/dev/null 2>&1 || true
    elif [[ "$CLEANUP" != "true" ]]; then
        print_warning "Skipping Helm cleanup"
    fi

    if [[ "$DESTROY_CLUSTER" == "true" && -n "$CLUSTER_NAME" ]]; then
        print_status "Deleting Kind cluster '$CLUSTER_NAME'..."
        kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
    elif [[ "$CLUSTER_CREATED" == "true" ]]; then
        print_status "Kind cluster '$CLUSTER_NAME' left running for reuse"
    fi
}

trap cleanup EXIT

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    parse_args "$@"
    KUBECONFIG_PATH="${KUBECONFIG_DIR}/kind-${CLUSTER_NAME}.config"

    if [[ "$CLEANUP_ONLY" == "true" ]]; then
        ensure_binary kind "kind CLI is required."
        if kind get clusters | grep -qw "$CLUSTER_NAME"; then
            mkdir -p "$KUBECONFIG_DIR"
            kind get kubeconfig --name "$CLUSTER_NAME" > "$KUBECONFIG_PATH"
            chmod 600 "$KUBECONFIG_PATH"
            export KUBECONFIG="$KUBECONFIG_PATH"
            KUBECONFIG_AVAILABLE="true"
            cleanup
        else
            print_warning "Kind cluster '$CLUSTER_NAME' not found; nothing to clean up"
        fi
        return 0
    fi

    print_status "Starting frontend integration tests..."

    ensure_kind_cluster
    check_kubectl
    check_helm
    check_docker

    build_and_load_image
    deploy_frontend

    get_frontend_url
    get_backend_url
    get_gluetun_url

    run_tests

    print_status "All tests completed successfully"
}

main "$@"
