# run_kind_e2e.sh - Unified Chart E2E Test Script

This script automates the complete end-to-end testing workflow for the **GeoSnappro unified Helm chart**.

## What It Does

The `run_kind_e2e.sh` script:

1. ✅ Creates or reuses a Kind cluster
2. ✅ Builds Docker images for all three services (screenshot-api, gluetun-api, frontend)
3. ✅ Loads images into the Kind cluster
4. ✅ Deploys the **UNIFIED Helm chart** (`charts/geosnappro`) with all services
5. ✅ Runs pytest tests to validate the deployment
6. ✅ Provides frontend access at port 5000

**Key Point**: This script deploys the **unified chart** (`charts/geosnappro/`), NOT separate charts!

## Quick Start

```bash
# Run the complete workflow
./tests/run_kind_e2e.sh

# Run without tests (deploy only)
SKIP_TESTS=false ./tests/run_kind_e2e.sh

# Skip Docker builds (faster if images already exist)
SKIP_BUILD=true ./tests/run_kind_e2e.sh
```

## Environment Variables

Customize the script with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLUSTER_NAME` | `geosnap-e2e` | Kind cluster name |
| `NAMESPACE` | `geosnap-e2e` | Kubernetes namespace |
| `RELEASE_NAME` | `geosnappro-e2e` | Helm release name for unified chart |
| `KEEP_CLUSTER` | `true` | Keep cluster after run |
| `SKIP_BUILD` | `false` | Skip Docker image builds |
| `SKIP_TESTS` | `true` | Skip pytest execution |
| `KIND_CONFIG` | `tests/kind/e2e-kind-config.yaml` | Kind cluster config |
| `IMAGE_TAG` | `kind-e2e` | Docker image tag |
| `FRONTEND_IMAGE_REPO` | `geosnap/frontend` | Frontend image repository |
| `SCREENSHOT_IMAGE_REPO` | `geosnap/screenshot-api` | Screenshot API repository |
| `GLUETUN_IMAGE_REPO` | `geosnap/gluetun-api` | Gluetun API repository |
| `PYTEST_ARGS` | `-v --tb=short` | Extra pytest arguments |

## Usage Examples

### Full Workflow (Build + Deploy + Test)

```bash
./tests/run_kind_e2e.sh
```

This will:
- Create Kind cluster
- Build all Docker images
- Deploy unified chart
- Run all pytest tests
- Keep cluster running for manual validation

### Deploy Only (No Tests)

```bash
SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

Then manually validate:
```bash
# Port forward to frontend
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e

# Visit http://localhost:5000 in your browser
```

### Skip Build (Use Existing Images)

```bash
SKIP_BUILD=true ./tests/run_kind_e2e.sh
```

Useful if you already have images from a previous run.

### Custom Cluster Name

```bash
CLUSTER_NAME=my-test NAMESPACE=my-test RELEASE_NAME=my-release ./tests/run_kind_e2e.sh
```

### Run Tests with Different Arguments

```bash
PYTEST_ARGS="-v -s --tb=long" ./tests/run_kind_e2e.sh
```

## What Gets Deployed

The script deploys the **unified Helm chart** at `charts/geosnappro/` which includes:

- ✅ **Screenshot API** (port 8000)
  - Image: `geosnap/screenshot-api:kind-e2e`
  - Service: `screenshot-api`
  
- ✅ **Gluetun API** (port 8001)
  - Image: `geosnap/gluetun-api:kind-e2e`
  - Service: `gluetun-api`
  - Includes RBAC for pod management
  
- ✅ **Frontend** (port 5000)
  - Image: `geosnap/frontend:kind-e2e`
  - Service: `frontend`

All from **ONE unified Helm chart**!

## Expected Output

```
==========================================
GeoSnappro Unified Chart E2E Test Runner
==========================================
Cluster: geosnap-e2e
Namespace: geosnap-e2e
Release: geosnappro-e2e
Chart: /home/david/repos/geosnappro-thefinal/charts/geosnappro
==========================================

[INFO]  Checking required tooling...
[INFO]  Ensuring Docker daemon is reachable...
[INFO]  Re-using existing Kind cluster geosnap-e2e
[INFO]  Building and loading Docker images into Kind cluster...
[INFO]  Building geosnap/gluetun-api:kind-e2e
[INFO]  Loading geosnap/gluetun-api:kind-e2e into Kind cluster geosnap-e2e
[INFO]  Building geosnap/screenshot-api:kind-e2e
[INFO]  Loading geosnap/screenshot-api:kind-e2e into Kind cluster geosnap-e2e
[INFO]  Building geosnap/frontend:kind-e2e
[INFO]  Loading geosnap/frontend:kind-e2e into Kind cluster geosnap-e2e
[INFO]  All images loaded successfully
[INFO]  Creating unified chart values file for all services
[INFO]  Creating namespace geosnap-e2e
[INFO]  Ensuring dummy WireGuard credentials secret exists
[INFO]  Deploying UNIFIED GeoSnappro Helm chart
[INFO]  Chart location: /home/david/repos/geosnappro-thefinal/charts/geosnappro
[INFO]  Release name: geosnappro-e2e
[INFO]  This will deploy: screenshot-api, gluetun-api, and frontend (all in one chart)
[INFO]  Waiting for all deployments from unified chart to become available
[INFO]  Unified chart deployment complete!
[INFO]  Services deployed:
NAME             TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
frontend         ClusterIP   10.96.123.45    <none>        5000/TCP   1m
gluetun-api      ClusterIP   10.96.123.46    <none>        8001/TCP   1m
screenshot-api   ClusterIP   10.96.123.47    <none>        8000/TCP   1m
[INFO]  Deployments:
NAME             READY   UP-TO-DATE   AVAILABLE   AGE
frontend         1/1     1            1           1m
gluetun-api      1/1     1            1           1m
screenshot-api   1/1     1            1           1m
==========================================
✅ All tests completed successfully!
==========================================
```

## Manual Validation

After the script completes (or with `SKIP_TESTS=true`), you can manually validate:

### Access Frontend

```bash
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e
```

Visit: **http://localhost:5000**

### Access Screenshot API

```bash
kubectl port-forward svc/screenshot-api 8000:8000 -n geosnap-e2e
curl http://localhost:8000/health
```

### Access Gluetun API

```bash
kubectl port-forward svc/gluetun-api 8001:8001 -n geosnap-e2e
curl http://localhost:8001/health
```

### Check Deployment Status

```bash
# View all resources from unified chart
kubectl get all -n geosnap-e2e -l app.kubernetes.io/instance=geosnappro-e2e

# View pods
kubectl get pods -n geosnap-e2e

# View services
kubectl get svc -n geosnap-e2e

# View logs
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=frontend
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=screenshot-api
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=gluetun-api
```

## Cleanup

### Automatic Cleanup

By default (`KEEP_CLUSTER=true`), the cluster is kept after tests. To automatically delete:

```bash
KEEP_CLUSTER=false ./tests/run_kind_e2e.sh
```

### Manual Cleanup

```bash
# Delete the entire cluster
kind delete cluster --name geosnap-e2e

# OR just uninstall the Helm release
helm uninstall geosnappro-e2e -n geosnap-e2e

# OR delete the namespace
kubectl delete namespace geosnap-e2e
```

## Troubleshooting

### Error: Chart Not Found

```
[ERROR] Unified chart not found at /home/david/repos/geosnappro-thefinal/charts/geosnappro
```

**Solution**: Ensure you're running from the project root and the unified chart exists at `charts/geosnappro/`.

### Error: Docker Daemon Not Reachable

```
[ERROR] Docker daemon is not reachable. Please start Docker.
```

**Solution**: Start Docker Desktop or Docker daemon.

### Error: Images Fail to Load

```
Error response from daemon: No such image: geosnap/frontend:kind-e2e
```

**Solution**: Don't use `SKIP_BUILD=true` on the first run. The script needs to build images first.

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -n geosnap-e2e

# View pod details
kubectl describe pod <pod-name> -n geosnap-e2e

# Check logs
kubectl logs <pod-name> -n geosnap-e2e
```

### Port Forward Fails

```bash
# Check if service exists
kubectl get svc -n geosnap-e2e

# Check if pods are running
kubectl get pods -n geosnap-e2e

# Try with a different local port
kubectl port-forward svc/frontend 8080:5000 -n geosnap-e2e
```

## Differences from Old Script

The **OLD** script deployed **three separate charts**:
- `charts/gluetun-api`
- `charts/screenshot-api`
- `charts/frontend`

The **NEW** script deploys **ONE unified chart**:
- `charts/geosnappro` (contains all three services)

### Migration Benefits

1. ✅ **Single Deployment** - One `helm install` instead of three
2. ✅ **Consistent Configuration** - All services share unified values
3. ✅ **Easier Management** - One release to manage
4. ✅ **Better Service Discovery** - Services automatically configured
5. ✅ **Simplified Testing** - One chart to test

## Integration with pytest

The script automatically exports environment variables for pytest:

```bash
export E2E_NAMESPACE="geosnap-e2e"
export E2E_RELEASE_NAME="geosnappro-e2e"
export E2E_CHART_PATH="/path/to/charts/geosnappro"
```

These are used by `test_kind_e2e.py` to:
- Connect to the correct namespace
- Use the correct Helm release name
- Validate the unified chart deployment

## Related Documentation

- **Unified Chart**: See `charts/geosnappro/README.md`
- **Deployment Guide**: See `charts/geosnappro/DEPLOYMENT.md`
- **Test Documentation**: See `tests/README-E2E.md`
- **Quick Test Guide**: See `tests/QUICK-TEST-GUIDE.md`

## Summary

✅ **Deploys unified Helm chart** (`charts/geosnappro`)  
✅ **All three services in one chart** (screenshot-api, gluetun-api, frontend)  
✅ **Automated build, deploy, test workflow**  
✅ **Frontend accessible at port 5000** for manual validation  
✅ **Keeps cluster running** for inspection  

**Quick command**: `./tests/run_kind_e2e.sh`

Happy testing! 🚀

