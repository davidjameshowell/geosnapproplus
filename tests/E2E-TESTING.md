# GeoSnappro End-to-End Testing Guide

## Overview

The E2E tests (`test_kind_e2e.py`) automatically deploy the unified GeoSnappro Helm chart to a Kubernetes cluster, set up port forwarding, and validate all services are functioning correctly.

## Features

✅ **Automatic Deployment** - Deploys the unified Helm chart before tests run  
✅ **Port Forwarding** - Automatically sets up port forwarding to all services  
✅ **Frontend on Port 5000** - Frontend is accessible on http://localhost:5000  
✅ **Service Validation** - Tests all service health endpoints  
✅ **Automatic Cleanup** - Tears down resources after tests complete  

## Prerequisites

### Required Tools

1. **Python 3.8+** with pytest and requests
   ```bash
   pip install pytest requests
   ```

2. **kubectl** - Kubernetes CLI
   ```bash
   # Verify installation
   kubectl version --client
   ```

3. **Helm 3.0+**
   ```bash
   # Verify installation
   helm version
   ```

4. **Kubernetes Cluster**
   - Kind (recommended for local testing)
   - Minikube
   - Docker Desktop with Kubernetes
   - Or any K8s cluster with kubectl access

### Setting Up Kind (Recommended)

```bash
# Install Kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Create a Kind cluster
kind create cluster --name geosnappro-e2e

# Verify cluster is running
kubectl cluster-info --context kind-geosnappro-e2e
```

## Running the Tests

### Basic Usage

```bash
# From the repository root
cd /home/david/repos/geosnappro-thefinal

# Run all E2E tests
pytest tests/test_kind_e2e.py -v -s
```

The `-s` flag is important to see the output including the frontend URL!

### What Happens During Test Execution

1. **Setup Phase** (before any tests):
   ```
   ================================================================================
   Setting up GeoSnappro E2E Test Environment
   ================================================================================
   Creating namespace geosnap-e2e...
   Creating WireGuard credentials secret...
   Deploying unified Helm chart from /path/to/charts/geosnappro...
   Release name: geosnappro-e2e, Namespace: geosnap-e2e
   Waiting for pods to be ready in namespace geosnap-e2e...
   All pods are ready!
   
   ================================================================================
   GeoSnappro E2E Environment Ready!
   ================================================================================
   ```

2. **Port Forwarding Setup**:
   - Gluetun API: http://localhost:28081
   - Screenshot API: http://localhost:28080
   - **Frontend: http://localhost:5000** ⭐

3. **Test Execution**:
   - Tests run against the forwarded ports
   - Each test validates a different aspect of the deployment

4. **Cleanup Phase** (after all tests):
   ```
   ================================================================================
   Cleaning up GeoSnappro E2E Test Environment
   ================================================================================
   Uninstalling Helm release geosnappro-e2e...
   Cleanup complete!
   ================================================================================
   ```

## Accessing the Frontend During Tests

### Option 1: Run Tests and Keep Environment Active

Skip cleanup to manually validate the frontend:

```bash
# Run tests but skip cleanup
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# Frontend will remain accessible at http://localhost:5000
# Press Ctrl+C when done to exit port forwarding
```

Then manually access:
- **Frontend**: http://localhost:5000
- **Screenshot API**: http://localhost:28080/docs
- **Gluetun API**: http://localhost:28081/docs

When done, clean up manually:
```bash
helm uninstall geosnappro-e2e -n geosnap-e2e
kubectl delete namespace geosnap-e2e
```

### Option 2: Deploy and Access Without Running Tests

Deploy manually for interactive testing:

```bash
# Create namespace
kubectl create namespace geosnap-e2e

# Create WireGuard secret
kubectl create secret generic gluetun-wireguard-credentials \
  --from-literal=wireguard-private-key=aCv31OvwOxhL7SzeSIAiQm1nXPw/pPNi+HPMj9rcxG8= \
  --from-literal=wireguard-addresses=10.68.50.98/32 \
  -n geosnap-e2e

# Deploy Helm chart
helm install geosnappro-e2e charts/geosnappro \
  --namespace geosnap-e2e \
  --wait \
  --timeout 5m

# Wait for pods
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=geosnappro-e2e \
  -n geosnap-e2e \
  --timeout=300s

# Set up port forwarding (run in separate terminals or use &)
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e &
kubectl port-forward svc/screenshot-api 28080:8000 -n geosnap-e2e &
kubectl port-forward svc/gluetun-api 28081:8001 -n geosnap-e2e &

# Visit http://localhost:5000 to access the frontend
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_NAMESPACE` | `geosnap-e2e` | Kubernetes namespace for deployment |
| `E2E_RELEASE_NAME` | `geosnappro-e2e` | Helm release name |
| `E2E_CHART_PATH` | `../charts/geosnappro` | Path to Helm chart |
| `E2E_PORT_FORWARD_TIMEOUT` | `60` | Seconds to wait for port forwarding |
| `E2E_HTTP_TIMEOUT` | `120` | Seconds to wait for HTTP responses |
| `E2E_POLL_INTERVAL` | `2.0` | Seconds between health check polls |
| `E2E_HELM_INSTALL_TIMEOUT` | `300` | Seconds to wait for Helm install |
| `E2E_SKIP_CLEANUP` | `false` | Skip cleanup after tests (for debugging) |

### Custom Configuration Example

```bash
# Use custom namespace and skip cleanup
E2E_NAMESPACE=my-test \
E2E_RELEASE_NAME=my-release \
E2E_SKIP_CLEANUP=true \
pytest tests/test_kind_e2e.py -v -s
```

## Test Cases

### 1. Gluetun API Health Check
- **Test**: `test_gluetun_health`
- **Validates**: Gluetun API is running and healthy
- **Endpoint**: http://localhost:28081/health

### 2. Gluetun Servers Preloaded
- **Test**: `test_gluetun_servers_preloaded`
- **Validates**: Mullvad servers are preloaded
- **Endpoint**: http://localhost:28081/servers

### 3. Screenshot API Health Check
- **Test**: `test_screenshot_api_health`
- **Validates**: Screenshot API is running and healthy
- **Endpoint**: http://localhost:28080/health

### 4. Frontend Homepage
- **Test**: `test_frontend_homepage`
- **Validates**: Frontend loads correctly with expected content
- **Endpoint**: http://localhost:5000

### 5. Frontend Port 5000 Accessibility ⭐
- **Test**: `test_frontend_port_5000_accessibility`
- **Validates**: Frontend is accessible on port 5000
- **Endpoint**: http://localhost:5000

## Troubleshooting

### Tests Fail to Deploy Chart

**Issue**: Helm chart deployment fails

**Solutions**:
```bash
# Check if cluster is accessible
kubectl cluster-info

# Verify Helm can access the chart
helm lint charts/geosnappro

# Check if namespace already exists
kubectl get namespace geosnap-e2e

# If namespace exists with resources, clean it up first
kubectl delete namespace geosnap-e2e
```

### Port Forwarding Fails

**Issue**: Cannot establish port forwarding

**Solutions**:
```bash
# Check if pods are running
kubectl get pods -n geosnap-e2e

# Check if services exist
kubectl get svc -n geosnap-e2e

# Check if ports are already in use
lsof -i :5000
lsof -i :28080
lsof -i :28081

# Kill processes using the ports
kill -9 <PID>
```

### Pods Not Ready

**Issue**: Pods stuck in Pending or CrashLoopBackOff

**Solutions**:
```bash
# Check pod status
kubectl get pods -n geosnap-e2e

# Describe problematic pod
kubectl describe pod <pod-name> -n geosnap-e2e

# Check logs
kubectl logs <pod-name> -n geosnap-e2e

# Common issues:
# 1. WireGuard credentials not created - check secret exists
kubectl get secret gluetun-wireguard-credentials -n geosnap-e2e

# 2. Insufficient resources - check cluster capacity
kubectl top nodes
kubectl describe nodes

# 3. Image pull issues - check events
kubectl get events -n geosnap-e2e --sort-by='.lastTimestamp'
```

### Tests Timeout

**Issue**: Tests hang or timeout waiting for services

**Solutions**:
```bash
# Increase timeouts
E2E_HTTP_TIMEOUT=300 \
E2E_HELM_INSTALL_TIMEOUT=600 \
pytest tests/test_kind_e2e.py -v -s

# Check if services are actually healthy
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e &
curl http://localhost:5000

kubectl port-forward svc/screenshot-api 8000:8000 -n geosnap-e2e &
curl http://localhost:8000/health

kubectl port-forward svc/gluetun-api 8001:8001 -n geosnap-e2e &
curl http://localhost:8001/health
```

### Frontend Not Accessible

**Issue**: Cannot access frontend on port 5000

**Solutions**:
```bash
# Verify frontend pod is running
kubectl get pods -n geosnap-e2e -l app.kubernetes.io/component=frontend

# Check frontend logs
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=frontend

# Verify service exists
kubectl get svc frontend -n geosnap-e2e

# Manually test port forward
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e
# Then visit http://localhost:5000
```

## Debugging

### Enable Verbose Output

```bash
# Maximum verbosity
pytest tests/test_kind_e2e.py -vv -s --log-cli-level=DEBUG
```

### Keep Environment for Debugging

```bash
# Run tests but don't clean up
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# Then inspect the cluster
kubectl get all -n geosnap-e2e
kubectl describe pods -n geosnap-e2e
kubectl logs -n geosnap-e2e --all-containers=true --prefix=true
```

### Run Specific Test

```bash
# Run only frontend test
pytest tests/test_kind_e2e.py::test_frontend_homepage -v -s

# Run only port 5000 validation
pytest tests/test_kind_e2e.py::test_frontend_port_5000_accessibility -v -s
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install pytest requests
      
      - name: Install Kind
        run: |
          curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
          chmod +x ./kind
          sudo mv ./kind /usr/local/bin/kind
      
      - name: Create Kind cluster
        run: kind create cluster --name geosnappro-e2e
      
      - name: Run E2E tests
        run: pytest tests/test_kind_e2e.py -v -s
      
      - name: Cleanup
        if: always()
        run: kind delete cluster --name geosnappro-e2e
```

## Manual Validation Workflow

For manual testing and validation:

```bash
# 1. Start tests with cleanup disabled
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# 2. Tests will output:
#    ✅ Frontend is accessible at: http://127.0.0.1:5000
#       You can validate manually by visiting: http://127.0.0.1:5000

# 3. Open browser and visit http://localhost:5000

# 4. Validate frontend functionality:
#    - Create a new screenshot task
#    - Check if it communicates with backend
#    - Verify VPN integration works

# 5. When done, clean up:
helm uninstall geosnappro-e2e -n geosnap-e2e
kubectl delete namespace geosnap-e2e
```

## Best Practices

1. **Use Kind for Local Testing**: Fast, isolated, disposable clusters
2. **Enable Skip Cleanup During Development**: Speeds up iteration
3. **Check Cluster Resources**: Ensure sufficient CPU/memory
4. **Monitor Logs**: Use `kubectl logs` to debug issues
5. **Clean Up Between Runs**: Prevents resource conflicts

## Summary

The E2E tests provide a comprehensive validation of the unified GeoSnappro Helm chart:

✅ Automated deployment and cleanup  
✅ Port forwarding to all services  
✅ Frontend accessible on port 5000  
✅ Health checks for all components  
✅ Easy to debug with `E2E_SKIP_CLEANUP`  
✅ CI/CD ready  

**Quick Start**: `pytest tests/test_kind_e2e.py -v -s`

**Frontend Access**: http://localhost:5000 (during or after tests with `E2E_SKIP_CLEANUP=true`)

For more information about the Helm chart, see:
- [Chart README](../charts/geosnappro/README.md)
- [Deployment Guide](../charts/geosnappro/DEPLOYMENT.md)
- [Quick Start](../charts/geosnappro/QUICK-START.md)

