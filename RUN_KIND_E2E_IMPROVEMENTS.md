# run_kind_e2e.sh Improvements - Image Rebuild & Rollout

## Summary

Enhanced the `tests/run_kind_e2e.sh` script to properly rebuild images and rollout updates when running against an existing cluster.

## Problem

Previously, when running the script against an existing cluster:
- Images were rebuilt and loaded
- Rollout restart happened **BEFORE** Helm upgrade
- This could cause race conditions or pods not picking up new images properly

## Solution

Reorganized the execution flow:

### New Execution Order

1. **Detect existing deployment** - Check if Helm release exists
2. **Build images** (if not skipped) - Rebuild all Docker images with latest code
3. **Load images into Kind** - Replace images in Kind's local registry
4. **Helm upgrade** - Update Helm release with latest configuration
5. **Rollout restart** (if existing deployment) - Force pods to recreate with new images

### Key Changes

#### 1. Moved Rollout Restart After Helm Upgrade

**Before** (`run_kind_e2e.sh` lines 419-423):
```bash
# If release exists and we just rebuilt images, rollout restart to use new images
if [ "$release_exists" = true ]; then
  log "Images updated. Rolling out new images to existing deployments..."
  rollout_restart_deployments
fi

# ... then helm upgrade happens later
```

**After** (`run_kind_e2e.sh` lines 448-459):
```bash
deploy_unified_chart

# If release existed and we rebuilt images, force rollout restart after helm upgrade
# This ensures pods pick up the newly loaded images with the same tag
if [ "$release_exists" = true ] && [[ "${SKIP_BUILD}" != "true" ]]; then
  log "🔄 ROLLING OUT NEW IMAGES"
  rollout_restart_deployments
  log "✅ All pods updated with new images!"
fi
```

#### 2. Enhanced Logging

Added clear messaging when existing deployment is detected:

```bash
if check_release_exists; then
  log "=========================================="
  log "⚙️  EXISTING DEPLOYMENT DETECTED"
  log "=========================================="
  log "Release '${RELEASE_NAME}' already exists in namespace '${NAMESPACE}'"
  log "The script will:"
  log "  1. Rebuild Docker images (frontend, screenshot-api, gluetun-api)"
  log "  2. Load updated images into Kind cluster"
  log "  3. Upgrade Helm release with latest configuration"
  log "  4. Force rollout restart to apply new images"
  log "=========================================="
  release_exists=true
fi
```

#### 3. Updated Documentation

Added behavior documentation in script header:

```bash
# Behavior with existing cluster:
#   If the cluster already exists, the script will:
#   1. Rebuild Docker images (unless SKIP_BUILD=true)
#   2. Load new images into the existing Kind cluster
#   3. Upgrade the Helm release with latest configuration
#   4. Force rollout restart to pick up the newly loaded images
```

## Usage

### Iterative Development (Most Common)

After making code changes, simply run:

```bash
./tests/run_kind_e2e.sh
```

**What happens:**
✅ Detects existing cluster  
✅ Rebuilds images with your changes  
✅ Loads updated images into Kind  
✅ Upgrades Helm release  
✅ Rolls out new images to pods  
✅ Runs tests (optional)  

### Quick Update Without Tests

```bash
SKIP_TESTS=true ./tests/run_kind_e2e.sh
```

Faster iteration - skips pytest execution.

### Configuration-Only Update

```bash
SKIP_BUILD=true ./tests/run_kind_e2e.sh
```

Updates Helm values without rebuilding images.

## Example Output

When running against an existing cluster:

```
[INFO]  ==========================================
[INFO]  GeoSnappro Unified Chart E2E Test Runner
[INFO]  ==========================================
[INFO]  Cluster: geosnap-e2e
[INFO]  Namespace: geosnap-e2e
[INFO]  Release: geosnappro-e2e
[INFO]  Chart: /path/to/charts/geosnappro
[INFO]  ==========================================
[INFO]  Re-using existing Kind cluster geosnap-e2e
[INFO]  ==========================================
[INFO]  ⚙️  EXISTING DEPLOYMENT DETECTED
[INFO]  ==========================================
[INFO]  Release 'geosnappro-e2e' already exists in namespace 'geosnap-e2e'
[INFO]  The script will:
[INFO]    1. Rebuild Docker images (frontend, screenshot-api, gluetun-api)
[INFO]    2. Load updated images into Kind cluster
[INFO]    3. Upgrade Helm release with latest configuration
[INFO]    4. Force rollout restart to apply new images
[INFO]  ==========================================
[INFO]  Building and loading Docker images into Kind cluster...
[INFO]  Building geosnap/gluetun-api:kind-e2e
...
[INFO]  ✅ All images built and loaded successfully
[INFO]  Creating unified chart values file for all services
[INFO]  Namespace geosnap-e2e already exists
[INFO]  Deploying UNIFIED GeoSnappro Helm chart
...
[INFO]  Unified chart deployment complete!
[INFO]  ==========================================
[INFO]  🔄 ROLLING OUT NEW IMAGES
[INFO]  ==========================================
[INFO]  Forcing rollout restart to pick up newly built images...
[INFO]  Rolling out updated images to existing deployments
[INFO]  Restarting deployment: frontend
[INFO]  Restarting deployment: gluetun-api
[INFO]  Restarting deployment: screenshot-api
[INFO]  Waiting for rollout to complete...
...
[INFO]  ==========================================
[INFO]  ✅ All pods updated with new images!
[INFO]  ==========================================
```

## Benefits

### For Developers

1. **Faster Iteration**: No need to delete/recreate cluster
2. **Reliable Updates**: Proper order ensures pods get new images
3. **Clear Feedback**: Enhanced logging shows exactly what's happening
4. **Flexible Control**: Environment variables for different scenarios

### Technical Improvements

1. **Correct Execution Order**: Helm upgrade before rollout restart
2. **Idempotent**: Can run multiple times safely
3. **Smart Detection**: Automatically handles existing vs fresh deployments
4. **Conditional Logic**: Only rollout restart when needed

## Testing

### Verify Image Updates

```bash
# Make a change to frontend/app.py
echo "# Test change" >> frontend/app.py

# Rebuild and deploy
SKIP_TESTS=true ./tests/run_kind_e2e.sh

# Check if new image is running
kubectl get pods -n geosnap-e2e -o wide
kubectl logs -n geosnap-e2e -l app.kubernetes.io/component=frontend | tail -20
```

### Verify Helm Upgrade

```bash
# Check release revision (should increment)
helm list -n geosnap-e2e

# Check release history
helm history geosnappro-e2e -n geosnap-e2e
```

## Related Documentation

- **`/docs/E2E_TESTING_GUIDE.md`** - Comprehensive guide for using the E2E test script
- **`/tests/run_kind_e2e.sh`** - The updated script itself

## Files Changed

1. **`tests/run_kind_e2e.sh`**
   - Moved rollout restart logic after helm upgrade (lines 448-459)
   - Enhanced logging for existing deployment detection (lines 415-425)
   - Updated script documentation header (lines 9-14)
   - Improved success messages (lines 433, 451-458)

2. **`docs/E2E_TESTING_GUIDE.md`** (NEW)
   - Complete guide for using the E2E test script
   - Usage scenarios and examples
   - Troubleshooting section
   - Performance tips

3. **`RUN_KIND_E2E_IMPROVEMENTS.md`** (this file)
   - Summary of changes
   - Before/after comparison
   - Usage examples

## Impact

✅ **Reliable image updates** when running against existing clusters  
✅ **Better developer experience** with clear feedback  
✅ **Faster iteration** during development  
✅ **Proper execution order** preventing race conditions  
✅ **Comprehensive documentation** for team use  

---

**Status**: ✅ **Complete and Ready**  
**Date**: November 18, 2025

