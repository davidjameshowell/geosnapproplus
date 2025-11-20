# E2E Test Updates - Summary

## Overview

Updated `test_kind_e2e.py` to include automatic deployment of the unified GeoSnappro Helm chart with port forwarding to port 5000 for frontend validation.

## What Changed

### ✅ Automatic Helm Chart Deployment

Added comprehensive deployment automation:

1. **Namespace Creation** - Automatically creates test namespace
2. **Secret Management** - Creates WireGuard credentials secret
3. **Helm Deployment** - Deploys unified chart with wait and timeout
4. **Pod Readiness** - Waits for all pods to be ready
5. **Automatic Cleanup** - Tears down resources after tests (optional)

### ✅ Frontend Port Forwarding to 5000

- **Changed frontend port forwarding** from `28082:5000` to `5000:5000`
- Frontend is now accessible at **http://localhost:5000** ⭐
- Matches standard port expectation for easier validation

### ✅ New Test Cases

Added new test: `test_frontend_port_5000_accessibility`
- Validates frontend is accessible on port 5000
- Provides clear output with access URL
- Confirms port forwarding is working correctly

### ✅ Enhanced Test Output

Tests now provide helpful output:
```
================================================================================
Testing Frontend at: http://127.0.0.1:5000
================================================================================
✅ Frontend is accessible at: http://127.0.0.1:5000
   You can validate manually by visiting: http://127.0.0.1:5000
================================================================================
```

## New Features

### 1. Session-Scoped Helm Deployment Fixture

```python
@pytest.fixture(scope="session")
def helm_deployment() -> None:
    """
    Deploy unified Helm chart before tests run.
    Automatically clean up after tests complete.
    """
```

**What it does**:
- Creates namespace
- Creates WireGuard secret
- Deploys Helm chart
- Waits for pods to be ready
- Cleans up after all tests (unless `E2E_SKIP_CLEANUP=true`)

### 2. Helper Functions

| Function | Purpose |
|----------|---------|
| `_run_command()` | Execute shell commands safely |
| `_create_namespace()` | Create K8s namespace if needed |
| `_create_wireguard_secret()` | Create WireGuard credentials |
| `_deploy_helm_chart()` | Deploy or upgrade Helm chart |
| `_wait_for_pods_ready()` | Wait for all pods to be ready |
| `_undeploy_helm_chart()` | Clean up Helm release |

### 3. Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_NAMESPACE` | `geosnap-e2e` | Test namespace |
| `E2E_RELEASE_NAME` | `geosnappro-e2e` | Helm release name |
| `E2E_CHART_PATH` | `../charts/geosnappro` | Path to unified chart |
| `E2E_HELM_INSTALL_TIMEOUT` | `300` | Helm install timeout (seconds) |
| `E2E_SKIP_CLEANUP` | `false` | Skip cleanup for debugging |

## Usage Examples

### Run Tests Normally

```bash
# Deploy, test, and cleanup automatically
pytest tests/test_kind_e2e.py -v -s
```

### Run Tests and Keep Environment

```bash
# Deploy and test, but skip cleanup for manual validation
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# Frontend remains accessible at http://localhost:5000
```

### Run Specific Test

```bash
# Test only frontend port 5000 accessibility
pytest tests/test_kind_e2e.py::test_frontend_port_5000_accessibility -v -s
```

### Use Custom Configuration

```bash
# Custom namespace and longer timeout
E2E_NAMESPACE=my-test \
E2E_HELM_INSTALL_TIMEOUT=600 \
pytest tests/test_kind_e2e.py -v -s
```

## Port Forwarding Configuration

Updated port forwarding targets:

```python
PORT_FORWARD_TARGETS = (
    ("svc/gluetun-api", 28081, 8001, "gluetun"),      # Gluetun API
    ("svc/screenshot-api", 28080, 8000, "screenshot"), # Screenshot API
    ("svc/frontend", 5000, 5000, "frontend"),          # Frontend on 5000 ⭐
)
```

### Service Access During Tests

- **Frontend**: http://localhost:5000 ⭐
- **Screenshot API**: http://localhost:28080
- **Gluetun API**: http://localhost:28081

## Test Flow

### 1. Setup (Before Tests)

```
================================================================================
Setting up GeoSnappro E2E Test Environment
================================================================================
Creating namespace geosnap-e2e...
Creating WireGuard credentials secret...
Deploying unified Helm chart from charts/geosnappro...
Release name: geosnappro-e2e, Namespace: geosnap-e2e
Helm chart deployed successfully!
Waiting for pods to be ready in namespace geosnap-e2e...
All pods are ready!

================================================================================
GeoSnappro E2E Environment Ready!
================================================================================
```

### 2. Port Forwarding Setup

Automatically establishes port forwarding to:
- Gluetun API (28081 → 8001)
- Screenshot API (28080 → 8000)
- Frontend (5000 → 5000) ⭐

### 3. Test Execution

All tests run with access to forwarded services:
- ✅ test_gluetun_health
- ✅ test_gluetun_servers_preloaded
- ✅ test_screenshot_api_health
- ✅ test_frontend_homepage
- ✅ test_frontend_port_5000_accessibility ⭐ (NEW)

### 4. Cleanup (After Tests)

```
================================================================================
Cleaning up GeoSnappro E2E Test Environment
================================================================================
Uninstalling Helm release geosnappro-e2e...
Cleanup complete!
================================================================================
```

## Benefits

### 1. **Complete Automation** ✅
No manual setup required - tests handle everything

### 2. **Easy Frontend Validation** ✅
Frontend accessible on standard port 5000

### 3. **Reproducible** ✅
Same deployment process across all test runs

### 4. **Debug-Friendly** ✅
Can skip cleanup to inspect environment

### 5. **CI/CD Ready** ✅
Fully automated for pipeline integration

### 6. **Unified Chart Testing** ✅
Tests the complete unified Helm chart deployment

## Manual Validation Workflow

Perfect for manual frontend validation:

```bash
# Step 1: Run tests with cleanup disabled
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# Step 2: Tests output the frontend URL:
# ✅ Frontend is accessible at: http://127.0.0.1:5000
#    You can validate manually by visiting: http://127.0.0.1:5000

# Step 3: Open browser to http://localhost:5000

# Step 4: Validate frontend functionality:
# - Create screenshot tasks
# - Test backend integration
# - Verify VPN functionality

# Step 5: When done, clean up manually:
helm uninstall geosnappro-e2e -n geosnap-e2e
kubectl delete namespace geosnap-e2e
```

## Files Modified

### Updated Files

1. **`tests/test_kind_e2e.py`**
   - Added Helm deployment automation
   - Changed frontend port to 5000
   - Added new test case
   - Enhanced output messages
   - Added configuration variables

### New Files

2. **`tests/E2E-TESTING.md`**
   - Comprehensive E2E testing guide
   - Setup instructions
   - Troubleshooting guide
   - CI/CD integration examples

3. **`tests/E2E-UPDATE-SUMMARY.md`** (this file)
   - Summary of changes
   - Usage examples

## Integration with Unified Chart

The E2E tests now fully integrate with the unified Helm chart:

- ✅ Deploys `charts/geosnappro` (unified chart)
- ✅ Uses chart's default service names
- ✅ Creates required secrets (WireGuard credentials)
- ✅ Validates all three services (screenshot-api, gluetun-api, frontend)
- ✅ Tests the complete application stack

## Prerequisites

To run the updated tests:

1. **Python 3.8+** with pytest and requests
2. **kubectl** - Kubernetes CLI
3. **Helm 3.0+**
4. **Kubernetes cluster** (Kind, Minikube, etc.)

### Quick Setup (Kind)

```bash
# Install Kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

# Create cluster
kind create cluster --name geosnappro-e2e

# Run tests
pytest tests/test_kind_e2e.py -v -s
```

## Troubleshooting

See `tests/E2E-TESTING.md` for detailed troubleshooting guide including:
- Port forwarding issues
- Pod readiness problems
- Chart deployment failures
- Frontend accessibility issues

## Next Steps

1. **Run the tests** to validate the unified chart deployment
   ```bash
   pytest tests/test_kind_e2e.py -v -s
   ```

2. **Validate frontend manually** using `E2E_SKIP_CLEANUP=true`
   ```bash
   E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s
   # Then visit http://localhost:5000
   ```

3. **Integrate with CI/CD** using the examples in `E2E-TESTING.md`

## Summary

✅ **Complete automation** - Helm chart deployment and cleanup  
✅ **Frontend on port 5000** - Easy access for validation  
✅ **New test cases** - Validates port 5000 accessibility  
✅ **Debug-friendly** - Skip cleanup for manual inspection  
✅ **Comprehensive docs** - Full testing guide provided  
✅ **Unified chart testing** - Tests complete application stack  

**Quick Start**: `pytest tests/test_kind_e2e.py -v -s`

**Frontend Validation**: `E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s` then visit http://localhost:5000

---

**Status**: ✅ COMPLETE - Ready for testing!

