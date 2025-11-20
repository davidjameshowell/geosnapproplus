# E2E Testing Guide - run_kind_e2e.sh

## Overview

The `tests/run_kind_e2e.sh` script provides automated end-to-end testing for the GeoSnappro stack using Kind (Kubernetes in Docker). It handles everything from cluster creation to deployment verification.

## Key Features

- ✅ **Automatic cluster management** - Creates Kind cluster if needed, reuses existing
- ✅ **Smart image handling** - Rebuilds and loads images into cluster
- ✅ **Unified Helm chart deployment** - Deploys all three services (frontend, screenshot-api, gluetun-api)
- ✅ **Intelligent upgrade handling** - Detects existing deployments and upgrades them properly
- ✅ **Automated testing** - Runs pytest-based health checks (optional)

## Usage Scenarios

### Scenario 1: First Run (Fresh Cluster)

Creates a new cluster, builds all images, and deploys everything:

```bash
./tests/run_kind_e2e.sh
```

**What happens:**
1. Creates Kind cluster `geosnap-e2e`
2. Builds Docker images for all 3 services
3. Loads images into Kind cluster
4. Creates namespace `geosnap-e2e`
5. Deploys unified Helm chart (fresh install)
6. Optionally runs pytest tests

### Scenario 2: Rebuild & Update Existing Cluster (Most Common)

When you've made code changes and want to test them in the existing cluster:

```bash
./tests/run_kind_e2e.sh
```

**What happens:**
1. Detects existing cluster and deployment
2. **Rebuilds all Docker images** with your latest code changes
3. **Loads updated images** into the existing Kind cluster
4. **Upgrades the Helm release** with latest configuration
5. **Forces rollout restart** to ensure pods use the new images
6. Optionally runs pytest tests

This is the **recommended workflow** for iterative development!

### Scenario 3: Update Configuration Only (Skip Rebuild)

When you only want to update Helm values without rebuilding images:

```bash
SKIP_BUILD=true ./tests/run_kind_e2e.sh
```

**What happens:**
1. Skips Docker image build
2. Updates Helm release with new values
3. Pods restart only if configuration changed

### Scenario 4: Deploy Only (No Tests)

Deploy/update the cluster but skip running pytest:

```bash
SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

Useful for manual testing or when you want to interact with the cluster.

### Scenario 5: Quick Update (Existing Cluster + No Tests)

Fastest iteration - rebuild and deploy without tests:

```bash
SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLUSTER_NAME` | `geosnap-e2e` | Name of the Kind cluster |
| `NAMESPACE` | `geosnap-e2e` | Kubernetes namespace for deployment |
| `RELEASE_NAME` | `geosnappro-e2e` | Helm release name |
| `KEEP_CLUSTER` | `true` | Keep cluster after run (false = delete) |
| `SKIP_BUILD` | `false` | Skip Docker image builds |
| `SKIP_TESTS` | `true` | Skip pytest execution |
| `IMAGE_TAG` | `kind-e2e` | Tag for built images |
| `FRONTEND_IMAGE_REPO` | `geosnap/frontend` | Frontend image repository |
| `SCREENSHOT_IMAGE_REPO` | `geosnap/screenshot-api` | Screenshot API image repository |
| `GLUETUN_IMAGE_REPO` | `geosnap/gluetun-api` | Gluetun API image repository |

### Examples

```bash
# Use custom cluster name
CLUSTER_NAME=my-test-cluster ./tests/run_kind_e2e.sh

# Delete cluster after run
KEEP_CLUSTER=false ./tests/run_kind_e2e.sh

# Skip everything, just deploy/upgrade
SKIP_BUILD=true SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

## Typical Development Workflow

### Initial Setup
```bash
# Create cluster and deploy everything
./tests/run_kind_e2e.sh
```

### Iterative Development
After making code changes:

```bash
# Rebuild images and update cluster
SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

This will:
- ✅ Rebuild only the changed services (fast incremental builds)
- ✅ Load new images into cluster
- ✅ Upgrade Helm release
- ✅ Rollout restart to apply changes
- ⏱️ Takes ~2-5 minutes depending on changes

### Manual Testing
```bash
# Port-forward to services
kubectl port-forward svc/frontend 5000:5000 -n geosnap-e2e &
kubectl port-forward svc/screenshot-api 8000:8000 -n geosnap-e2e &
kubectl port-forward svc/gluetun-api 8001:8001 -n geosnap-e2e &

# Test frontend
curl http://localhost:5000

# Test screenshot API
curl http://localhost:8000/health

# Test gluetun API
curl http://localhost:8001/health

# Test VPN locations
curl http://localhost:5000/api/gluetun/locations | jq '.total_servers'
```

### Cleanup
```bash
# Delete the cluster when done
kind delete cluster --name geosnap-e2e
```

## How Image Updates Work

The script uses a smart approach to ensure new images are used:

1. **Image Tag Strategy**: All images use the same tag (`kind-e2e` by default)
2. **Load into Kind**: `kind load docker-image` replaces the image in the cluster
3. **Helm Upgrade**: Updates configuration and secrets
4. **Rollout Restart**: Forces pods to be recreated with new images

This works because:
- Kind's local registry is updated with the new image
- Kubernetes uses `imagePullPolicy: IfNotPresent` by default
- Rollout restart recreates pods, forcing them to pull from Kind's local registry
- Even though the tag is the same, the image content is different

## Troubleshooting

### Images Not Updating

**Symptom**: Code changes aren't reflected in pods

**Solution**: Make sure you're not using `SKIP_BUILD=true`

```bash
# Force rebuild everything
./tests/run_kind_e2e.sh
```

### Pods Stuck in ImagePullBackOff

**Symptom**: Pods can't pull images

**Cause**: Image wasn't loaded into Kind cluster

**Solution**: Rebuild and reload images

```bash
./tests/run_kind_e2e.sh
```

### Helm Upgrade Fails

**Symptom**: Helm upgrade returns an error

**Solution**: Check logs and values

```bash
# Check current release
helm list -n geosnap-e2e

# Check release status
helm status geosnappro-e2e -n geosnap-e2e

# If needed, delete and recreate
helm uninstall geosnappro-e2e -n geosnap-e2e
./tests/run_kind_e2e.sh
```

### Cluster Issues

**Symptom**: Cluster not accessible or corrupted

**Solution**: Delete and recreate

```bash
kind delete cluster --name geosnap-e2e
./tests/run_kind_e2e.sh
```

## Logs and Debugging

### Check Pod Logs
```bash
# All pods
kubectl get pods -n geosnap-e2e

# Frontend logs
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=frontend

# Screenshot API logs
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=screenshot-api

# Gluetun API logs
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=gluetun-api

# Follow logs in real-time
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=frontend -f
```

### Check Deployment Status
```bash
# All deployments
kubectl get deployments -n geosnap-e2e

# Detailed deployment info
kubectl describe deployment frontend -n geosnap-e2e

# Rollout status
kubectl rollout status deployment/frontend -n geosnap-e2e
```

### Check Services
```bash
# List services
kubectl get svc -n geosnap-e2e

# Check endpoints
kubectl get endpoints -n geosnap-e2e
```

## Performance Tips

### Faster Iterations

1. **Use incremental builds**: Docker caches layers, so only changed files rebuild
2. **Skip tests during development**: Use `SKIP_TESTS=true`
3. **Keep cluster running**: Set `KEEP_CLUSTER=true` (default)
4. **Use multiple terminals**: Keep port-forwards running in background

### Build Time Optimization

```bash
# First run (cold cache): ~5-10 minutes
./tests/run_kind_e2e.sh

# Subsequent runs (warm cache): ~2-3 minutes
SKIP_TESTS=true ./tests/run_kind_e2e.sh

# Config-only update: ~30 seconds
SKIP_BUILD=true SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

## Related Files

- `/tests/run_kind_e2e.sh` - Main script
- `/tests/kind/e2e-kind-config.yaml` - Kind cluster configuration
- `/tests/test_kind_e2e.py` - Pytest test suite
- `/tests/requirements.txt` - Python test dependencies
- `/charts/geosnappro/` - Unified Helm chart

## Additional Resources

- [Kind Documentation](https://kind.sigs.k8s.io/)
- [Helm Documentation](https://helm.sh/docs/)
- [Kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)

