# Kubernetes Pod Errors - All Fixed ✅

## Summary
Examined all pods in the `geosnap-e2e` namespace and resolved all errors found in the logs.

## Issues Found & Resolved

### 1. Frontend Permission Errors ❌ → ✅

#### Problem
The frontend pod was experiencing repeated permission errors when trying to write screenshots to `/app/media/`:
```
PermissionError: [Errno 13] Permission denied: '/app/media/50dc277a79924b03b7e601ea6c954fcd.png'
```

#### Root Cause
The Kubernetes deployment runs the frontend container as user ID 1000 (non-root) for security, but the old Docker image was creating the `/app/media` directory as root, causing permission conflicts with the mounted PersistentVolume.

#### Solution Applied
1. **Updated `frontend/Dockerfile`**:
   - Created a non-root user `appuser` with UID/GID 1000
   - Set proper ownership of `/app/media` directory
   - Configured container to run as `appuser`

2. **Rebuilt and reloaded the image**:
   ```bash
   cd frontend
   docker build -t geosnap/frontend:kind-e2e .
   kind load docker-image geosnap/frontend:kind-e2e --name geosnap-e2e
   kubectl rollout restart deployment -n geosnap-e2e frontend
   ```

#### Verification
```bash
# Check user
kubectl exec -n geosnap-e2e frontend-77556c77cc-l4k4x -- id
# Output: uid=1000(appuser) gid=1000(appuser) groups=1000(appuser)

# Check permissions
kubectl exec -n geosnap-e2e frontend-77556c77cc-l4k4x -- ls -la /app/media/
# Output: drwxr-xr-x 1 appuser appuser 4096 Nov 18 17:51 .
```

### 2. VPN Locations Showing Only 1 Server ❌ → ✅

#### Problem
The frontend's `/api/gluetun/locations` endpoint was only returning 1 VPN server (Stockholm, Sweden) instead of 500+ servers.

#### Root Cause
The E2E test deployment had `SERVERS_JSON` environment variable set to a minimal test configuration, which overrode the bundled `servers.json` file containing 532 servers.

#### Solution Applied
1. **Updated ConfigMap**:
   ```bash
   kubectl patch configmap -n geosnap-e2e gluetun-api-config \
     --type='json' \
     -p='[{"op": "replace", "path": "/data/SERVERS_JSON", "value": ""}]'
   ```

2. **Restarted gluetun-api**:
   ```bash
   kubectl rollout restart deployment -n geosnap-e2e gluetun-api
   ```

3. **Updated E2E test script** (`tests/run_kind_e2e.sh`):
   - Changed line 114-116 to use empty `servers_json` instead of test data
   - Future E2E runs will use the full server list

#### Verification
```bash
curl http://localhost:5000/api/gluetun/locations
```
Result:
```json
{
  "total_servers": 532,
  "total_countries": 49,
  "total_cities": 89
}
```

## Current Pod Status

All pods running without errors:

```bash
kubectl get pods -n geosnap-e2e
```

```
NAME                              READY   STATUS    RESTARTS   AGE
frontend-77556c77cc-l4k4x         1/1     Running   0          5m
gluetun-api-5c579fdc54-mbrh4      1/1     Running   0          15m
screenshot-api-786df46948-5cvvc   1/1     Running   0          3h
```

### Pod Log Status
✅ **frontend**: No errors, media directory initialized successfully  
✅ **gluetun-api**: No errors, 532 servers loaded from bundled file  
✅ **screenshot-api**: No errors  

## Files Modified

1. **`/frontend/Dockerfile`**
   - Added non-root user creation (UID 1000)
   - Set proper file ownership
   - Configured container to run as non-root

2. **`/frontend/app.py`**
   - Enhanced error handling for media directory initialization
   - Added permission testing on startup
   - Better logging for debugging

3. **`/tests/run_kind_e2e.sh`**
   - Changed test configuration to use bundled servers.json
   - Line 114-116: `servers_json=''` instead of test data

4. **Kubernetes ConfigMap** (runtime change)
   - Namespace: `geosnap-e2e`
   - ConfigMap: `gluetun-api-config`
   - Set `SERVERS_JSON` to empty string

## Testing & Verification

### Test 1: Frontend Health
```bash
kubectl port-forward -n geosnap-e2e svc/frontend 5000:5000
curl http://localhost:5000/
# ✅ Returns HTML homepage
```

### Test 2: VPN Locations
```bash
curl http://localhost:5000/api/gluetun/locations
# ✅ Returns 532 servers across 49 countries
```

### Test 3: Media Directory
```bash
kubectl exec -n geosnap-e2e frontend-77556c77cc-l4k4x -- ls -la /app/media/
# ✅ Shows files owned by appuser with correct permissions
```

### Test 4: Check Logs for Errors
```bash
for pod in $(kubectl get pods -n geosnap-e2e -o name); do 
  kubectl logs -n geosnap-e2e $pod --tail=100 | grep -iE "error|exception"
done
# ✅ No errors in any pod
```

## Documentation Created

1. **`/docs/GLUETUN_SERVER_CONFIGURATION.md`**
   - Complete guide on server configuration
   - Loading priority explanation
   - Troubleshooting steps

2. **`/K8S_VPN_LOCATIONS_FIX.md`**
   - Summary of VPN locations fix
   - Future deployment instructions

3. **`/K8S_POD_ERRORS_FIXED.md`** (this file)
   - Comprehensive summary of all fixes
   - Verification steps

## For Future Deployments

### Production
All fixes are now in the codebase. For production deployments:
```bash
# Build images with fixes
docker build -t your-registry/frontend:latest ./frontend

# Deploy with production values (already configured correctly)
helm upgrade --install geosnappro ./charts/geosnappro \
  -f charts/geosnappro/values-production.yaml
```

### E2E Testing
The updated E2E script now uses the full server list:
```bash
./tests/run_kind_e2e.sh
```

## Impact Summary

✅ **Frontend**: Permission errors resolved, media files saving successfully  
✅ **VPN Locations**: Full server list available (532 servers, 49 countries)  
✅ **All Pods**: Running without errors or warnings  
✅ **E2E Tests**: Updated to use proper configuration  
✅ **Documentation**: Comprehensive guides created for future reference  

## Related Pull Requests / Commits

All changes have been made to the local repository and are ready to be committed:
- Frontend Dockerfile updates
- Frontend app.py error handling improvements
- E2E test script configuration fix
- Documentation additions

---

**Status**: ✅ **All Issues Resolved**  
**Date**: November 18, 2025  
**Namespace**: `geosnap-e2e`

