# GeoSnappro E2E Tests - Unified Chart

This directory contains end-to-end tests that validate the **unified GeoSnappro Helm chart** deployment.

## Overview

The E2E tests (`test_kind_e2e.py`) deploy the **complete unified Helm chart** from `charts/geosnappro/` and validate that all three services work correctly:

- ✅ **Screenshot API** (port 8000)
- ✅ **Gluetun API** (port 8001)
- ✅ **Frontend** (port 5000)

All services are deployed from a **single unified Helm chart**, not separate charts.

## What the Tests Do

### 1. Setup Phase
1. Creates Kubernetes namespace (`geosnap-e2e` by default)
2. Creates WireGuard credentials secret (using example credentials from `docker-compose.yml`)
3. Deploys the **unified Helm chart** at `charts/geosnappro/`
4. Waits for all pods to be ready

### 2. Port Forwarding
Sets up local access to all services:
- `http://127.0.0.1:5000` → Frontend (port 5000)
- `http://127.0.0.1:28080` → Screenshot API (port 8000)
- `http://127.0.0.1:28081` → Gluetun API (port 8001)

### 3. Test Validation
- **Unified Chart Deployment**: Verifies all three services are deployed
- **Gluetun API Health**: Tests `/health` endpoint
- **Gluetun Servers**: Verifies Mullvad servers are preloaded
- **Screenshot API Health**: Tests `/health` endpoint
- **Frontend Homepage**: Validates UI loads correctly
- **Frontend Port 5000**: Confirms frontend is accessible on port 5000

### 4. Cleanup Phase
Automatically uninstalls the Helm release after tests complete (unless `E2E_SKIP_CLEANUP` is set).

## Prerequisites

### Required

1. **Kubernetes Cluster** (Kind, Minikube, or K3s)
   ```bash
   # Example with Kind
   kind create cluster --name geosnappro-test
   ```

2. **Helm 3.x**
   ```bash
   helm version
   ```

3. **Python 3.10+** with dependencies
   ```bash
   pip install -r requirements.txt
   # or if you have a separate test requirements file:
   pip install pytest requests
   ```

### Optional

- **kubectl** configured to access your cluster
- **Docker** (for Kind/Minikube)

## Running the Tests

### Quick Start

```bash
# From the project root
cd /home/david/repos/geosnappro-thefinal

# Run all E2E tests
pytest tests/test_kind_e2e.py -v -s
```

The `-s` flag is recommended to see the detailed output including URLs for manual validation.

### Run Specific Tests

```bash
# Test only the unified chart deployment
pytest tests/test_kind_e2e.py::test_unified_chart_all_services_deployed -v -s

# Test only the frontend
pytest tests/test_kind_e2e.py::test_frontend_homepage -v -s
pytest tests/test_kind_e2e.py::test_frontend_port_5000_accessibility -v -s

# Test only the APIs
pytest tests/test_kind_e2e.py::test_gluetun_health -v -s
pytest tests/test_kind_e2e.py::test_screenshot_api_health -v -s
```

## Environment Variables

Customize test behavior with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_NAMESPACE` | `geosnap-e2e` | Kubernetes namespace for tests |
| `E2E_RELEASE_NAME` | `geosnappro-e2e` | Helm release name |
| `E2E_CHART_PATH` | `charts/geosnappro` | Path to unified Helm chart |
| `E2E_HELM_INSTALL_TIMEOUT` | `300` | Helm install timeout (seconds) |
| `E2E_PORT_FORWARD_TIMEOUT` | `60` | Port forward timeout (seconds) |
| `E2E_HTTP_TIMEOUT` | `120` | HTTP request timeout (seconds) |
| `E2E_POLL_INTERVAL` | `2.0` | Poll interval for retries (seconds) |
| `E2E_SKIP_CLEANUP` | `false` | Skip cleanup after tests |

### Example with Custom Settings

```bash
# Use custom namespace and skip cleanup
E2E_NAMESPACE=my-test E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# Use longer timeouts for slow clusters
E2E_HELM_INSTALL_TIMEOUT=600 E2E_HTTP_TIMEOUT=300 pytest tests/test_kind_e2e.py -v -s
```

## Manual Frontend Validation

When the tests run, they will output the frontend URL. You can manually validate the UI:

1. **Run the tests** (they will keep port forwarding active):
   ```bash
   pytest tests/test_kind_e2e.py -v -s
   ```

2. **Watch for the output**:
   ```
   ================================================================================
   ✅ Frontend Validation Successful!
   ================================================================================
   Frontend is accessible at: http://127.0.0.1:5000
   
   📋 Manual Validation Steps:
      1. Open your browser
      2. Navigate to: http://127.0.0.1:5000
      3. You should see the 'Capture Any Website' interface
      4. Verify you can interact with the UI
   
   💡 This frontend was deployed from the unified Helm chart
      Location: charts/geosnappro/
   ================================================================================
   ```

3. **Open the URL** in your browser: http://127.0.0.1:5000

4. **Validate the UI**:
   - ✅ Page loads correctly
   - ✅ "Capture Any Website" heading is visible
   - ✅ "Create New Task" button is present
   - ✅ UI is interactive and responsive

### Keep Environment Running for Manual Testing

To keep the deployment and port forwards active after tests:

```bash
# Set E2E_SKIP_CLEANUP to prevent uninstall
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# In another terminal, manually set up port forwarding
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e
kubectl port-forward svc/screenshot-api 8000:8000 -n geosnap-e2e
kubectl port-forward svc/gluetun-api 8001:8001 -n geosnap-e2e

# Access the services
# Frontend:       http://localhost:5000
# Screenshot API: http://localhost:8000
# Gluetun API:    http://localhost:8001
```

## Expected Test Output

```
================================================================================
🚀 Setting up GeoSnappro E2E Test Environment
================================================================================
📦 Deploying UNIFIED Helm Chart (all services in one chart)
================================================================================

Step 1/4: Creating namespace...
✅ Namespace 'geosnap-e2e' ready

Step 2/4: Setting up WireGuard credentials...
✅ WireGuard secret created

Step 3/4: Deploying unified Helm chart...

================================================================================
Deploying UNIFIED GeoSnappro Helm Chart
================================================================================
Chart path: /home/david/repos/geosnappro-thefinal/charts/geosnappro
Release name: geosnappro-e2e
Namespace: geosnap-e2e
This will deploy: screenshot-api, gluetun-api, and frontend
================================================================================

✅ Helm chart deployed

Step 4/4: Waiting for all pods to be ready...
✅ All pods are ready


================================================================================
✅ GeoSnappro E2E Environment Ready!
================================================================================
📦 Unified chart deployed with:
   • Screenshot API (port 8000)
   • Gluetun API (port 8001)
   • Frontend (port 5000)
================================================================================


================================================================================
🔌 Setting up Port Forwarding for Unified Chart Services
================================================================================
Port forwarding: svc/gluetun-api -> 127.0.0.1:28081
Port forwarding: svc/screenshot-api -> 127.0.0.1:28080
Port forwarding: svc/frontend -> 127.0.0.1:5000

✅ Port Forwarding Active!
================================================================================
Access Services:
  • Frontend:       http://127.0.0.1:5000
  • Screenshot API: http://127.0.0.1:28080
  • Gluetun API:    http://127.0.0.1:28081
================================================================================

tests/test_kind_e2e.py::test_gluetun_health PASSED
tests/test_kind_e2e.py::test_gluetun_servers_preloaded PASSED
tests/test_kind_e2e.py::test_screenshot_api_health PASSED
tests/test_kind_e2e.py::test_frontend_homepage PASSED
tests/test_kind_e2e.py::test_frontend_port_5000_accessibility PASSED
tests/test_kind_e2e.py::test_unified_chart_all_services_deployed PASSED

================================================================================
🧹 Cleaning up GeoSnappro E2E Test Environment
================================================================================
✅ Cleanup complete!
================================================================================
```

## Troubleshooting

### Test Fails: Chart Not Found

```
FileNotFoundError: Unified Helm chart not found at charts/geosnappro
```

**Solution**: Ensure you're running tests from the project root:
```bash
cd /home/david/repos/geosnappro-thefinal
pytest tests/test_kind_e2e.py -v -s
```

### Test Fails: Pods Not Ready

```
TimeoutError: Timed out waiting for pods to be ready
```

**Solutions**:
1. Check cluster has enough resources
2. View pod status: `kubectl get pods -n geosnap-e2e`
3. Check pod logs: `kubectl logs -n geosnap-e2e -l app.kubernetes.io/instance=geosnappro-e2e`
4. Increase timeout: `E2E_HELM_INSTALL_TIMEOUT=600 pytest tests/test_kind_e2e.py -v -s`

### Port Forward Fails

```
TimeoutError: Timed out waiting for port 127.0.0.1:5000
```

**Solutions**:
1. Check if services are running: `kubectl get svc -n geosnap-e2e`
2. Verify pods are ready: `kubectl get pods -n geosnap-e2e`
3. Check for port conflicts: `lsof -i :5000`

### Frontend Test Fails

```
AssertionError: Expected 'Capture Any Website' in response
```

**Solutions**:
1. Check frontend logs: `kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=frontend`
2. Verify frontend pod is running: `kubectl get pods -n geosnap-e2e -l app.kubernetes.io/component=frontend`
3. Test manually: `curl http://127.0.0.1:5000`

## Manual Cleanup

If tests are interrupted or `E2E_SKIP_CLEANUP` is set:

```bash
# Uninstall the Helm release
helm uninstall geosnappro-e2e -n geosnap-e2e

# Delete the namespace (optional)
kubectl delete namespace geosnap-e2e

# Delete WireGuard secret (if namespace not deleted)
kubectl delete secret gluetun-wireguard-credentials -n geosnap-e2e
```

## What Makes This Test "Unified"

The test validates the **unified Helm chart** approach where:

1. ✅ **Single Chart** - All services in `charts/geosnappro/`
2. ✅ **Single Install** - One `helm install` command deploys everything
3. ✅ **Single Release** - One Helm release manages all services
4. ✅ **Consistent Config** - Shared values file for all components
5. ✅ **Service Discovery** - Services automatically find each other

This is different from having separate charts for each service.

## Verifying Unified Chart Structure

The test includes `test_unified_chart_all_services_deployed()` which explicitly verifies:
- All three deployments exist (screenshot-api, gluetun-api, frontend)
- All three services exist
- All are labeled with the same Helm release name
- All were deployed from the unified chart

## Integration with CI/CD

Example GitHub Actions workflow:

```yaml
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Create Kind cluster
        uses: helm/kind-action@v1
        
      - name: Install Helm
        uses: azure/setup-helm@v3
        
      - name: Run E2E tests
        run: |
          pip install pytest requests
          pytest tests/test_kind_e2e.py -v
```

## Summary

✅ **Tests deploy the UNIFIED Helm chart** from `charts/geosnappro/`  
✅ **All three services deployed together**: screenshot-api, gluetun-api, frontend  
✅ **Port forwarding to 5000** for frontend validation  
✅ **Manual validation instructions** printed during test run  
✅ **Automatic cleanup** after tests complete  

**To run tests and validate frontend:**
```bash
pytest tests/test_kind_e2e.py -v -s
# Then open http://127.0.0.1:5000 in your browser
```

Happy testing! 🚀

