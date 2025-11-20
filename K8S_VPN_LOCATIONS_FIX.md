# K8s VPN Locations Fix - Summary

## Problem
When running the frontend in Kubernetes (geosnap-e2e namespace), the VPN locations endpoint only showed 1 server (Stockholm, Sweden) instead of the full list of 500+ Mullvad servers.

## Root Cause
The E2E test deployment was using a test configuration with `SERVERS_JSON` environment variable set to a minimal single-server configuration. This overrode the bundled `servers.json` file that contains the full server list.

The application loads servers in this priority:
1. `SERVERS_JSON` env var (was set to test data) ❌
2. `SERVERS_FILE_PATH` env var (was empty)
3. Bundled `/app/data/servers.json` file (contains 532 servers) ✅ (what we want)

## Solution Applied

### 1. Fixed Current Deployment
```bash
# Updated ConfigMap to empty SERVERS_JSON
kubectl patch configmap -n geosnap-e2e gluetun-api-config \
  --type='json' \
  -p='[{"op": "replace", "path": "/data/SERVERS_JSON", "value": ""}]'

# Restarted deployment
kubectl rollout restart deployment -n geosnap-e2e gluetun-api
```

### 2. Updated E2E Test Script
Modified `/tests/run_kind_e2e.sh` to use empty `SERVERS_JSON` instead of test configuration, allowing the bundled file to be used.

### 3. Created Documentation
Added comprehensive guide at `/docs/GLUETUN_SERVER_CONFIGURATION.md` explaining:
- How server loading works
- How to configure for different environments
- Troubleshooting steps
- Verification methods

## Verification Results

After the fix, both the Gluetun API and Frontend now return the full server list:

```json
{
  "total_countries": 49,
  "total_cities": 89,
  "total_servers": 532
}
```

Sample countries now include: Albania, Australia, Austria, Belgium, Brazil, and 44 more!

## Files Changed

1. **`/tests/run_kind_e2e.sh`**
   - Changed test server configuration to use bundled file
   - Line 114-116: Set `servers_json=''` instead of test configuration

2. **`/docs/GLUETUN_SERVER_CONFIGURATION.md`** (NEW)
   - Complete guide for server configuration
   - Troubleshooting steps
   - Best practices

3. **ConfigMap in K8s** (runtime change)
   - Namespace: `geosnap-e2e`
   - ConfigMap: `gluetun-api-config`
   - Changed `SERVERS_JSON` from test data to empty string

## For Future Deployments

### Production
Use the production values file which doesn't override SERVERS_JSON:
```bash
helm upgrade --install geosnappro ./charts/geosnappro \
  -f charts/geosnappro/values-production.yaml \
  --set gluetunApi.wireguard.privateKey="YOUR_KEY" \
  --set gluetunApi.wireguard.addresses="YOUR_ADDRESSES"
```

### E2E Testing
The updated E2E script now uses the full server list by default. Run as normal:
```bash
./tests/run_kind_e2e.sh
```

### Custom Deployments
In your Helm values, ensure these are empty to use the bundled file:
```yaml
gluetunApi:
  config:
    serversFilePath: ""
    serversJSON: ""
```

## Impact
- ✅ Frontend now shows all 532 Mullvad servers
- ✅ Users can select from 49 countries and 89 cities
- ✅ E2E tests will use full server list going forward
- ✅ Production deployments will work correctly by default

## Related Issues
This also resolves the frontend permission error that was fixed earlier by updating the frontend Dockerfile to run as non-root user (UID 1000).

