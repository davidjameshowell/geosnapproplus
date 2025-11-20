# Gluetun Server Configuration Guide

## Overview

The Gluetun K8s API needs access to a list of Mullvad VPN servers to function properly. This document explains how server data is loaded and how to configure it correctly.

## Server Loading Priority

The Gluetun API attempts to load server data in the following order:

1. **`SERVERS_JSON` environment variable** (highest priority)
   - A JSON string containing the full server list
   - If set (even to a test value), overrides all other sources

2. **`SERVERS_FILE_PATH` environment variable**
   - Path to a JSON file containing server data
   - If set and file exists, will be used

3. **Bundled file at `/app/data/servers.json`** (default)
   - Built into the Docker image
   - Contains 500+ Mullvad servers across 49 countries
   - **This is the recommended source for most deployments**

4. **Kubernetes Job fallback**
   - Spawns a temporary Gluetun container to fetch current server list
   - Only used if all above methods fail

## Problem: Test Configuration in Production

### Issue

If you see only 1 server (Stockholm, Sweden) when running in Kubernetes, it's because the `SERVERS_JSON` environment variable is set to a test configuration:

```json
{
  "mullvad": {
    "servers": [
      {
        "hostname": "test.mullvad.net",
        "country": "Sweden",
        "city": "Stockholm",
        "vpn": "wireguard"
      }
    ]
  }
}
```

### Root Cause

The E2E test script (`tests/run_kind_e2e.sh`) was originally configured to use a minimal test server list to speed up testing. This test configuration should not be used for actual deployments.

## Solution

### Quick Fix (For Running Deployment)

If you already have a deployment with the test configuration:

```bash
# Set SERVERS_JSON to empty string (let it use bundled file)
kubectl patch configmap -n <your-namespace> gluetun-api-config \
  --type='json' \
  -p='[{"op": "replace", "path": "/data/SERVERS_JSON", "value": ""}]'

# Restart the deployment
kubectl rollout restart deployment -n <your-namespace> gluetun-api

# Verify the fix (wait ~30 seconds for pod to be ready)
kubectl logs -n <your-namespace> -l app.kubernetes.io/name=gluetun-api | grep "Loaded.*servers"
```

You should see: `Loaded 532 Mullvad servers from bundled file '/app/data/servers.json'`

### Proper Configuration for Helm Deployments

In your `values.yaml` or values override file:

```yaml
gluetunApi:
  config:
    # Leave these empty to use the bundled servers.json file
    serversFilePath: ""
    serversJSON: ""
    
    # Optional: Use a preloaded ConfigMap (not required)
    preloadedServersConfigMap: ""
```

### Production Best Practice

For production deployments, use the `values-production.yaml` as a template, which already has the correct configuration (no SERVERS_JSON override):

```bash
helm upgrade --install geosnappro ./charts/geosnappro \
  --namespace geosnap-prod \
  --create-namespace \
  -f charts/geosnappro/values-production.yaml \
  --set gluetunApi.wireguard.privateKey="YOUR_KEY" \
  --set gluetunApi.wireguard.addresses="YOUR_ADDRESSES"
```

## Verification

After deployment, verify the server count:

### Check Gluetun API Directly

```bash
kubectl port-forward -n <namespace> svc/gluetun-api 8001:8001 &
curl http://localhost:8001/locations | jq '.total_servers'
```

Expected result: `532` (or similar, depending on Mullvad's current server count)

### Check Frontend Proxy Endpoint

```bash
kubectl port-forward -n <namespace> svc/frontend 5000:5000 &
curl http://localhost:5000/api/gluetun/locations | jq '.total_servers'
```

Expected result: Same as above

### Check Pod Logs

```bash
kubectl logs -n <namespace> -l app.kubernetes.io/name=gluetun-api | grep "Loaded"
```

Expected output:
```
Loaded 532 Mullvad servers from bundled file '/app/data/servers.json'.
```

## Updating the Bundled Server List

The bundled `servers.json` file is built into the Docker image. To update it:

1. Update `/gluetun-k8s/data/servers.json` in the repository
2. Rebuild the Docker image:
   ```bash
   cd gluetun-k8s
   docker build -t your-registry/gluetun-k8s-api:latest .
   docker push your-registry/gluetun-k8s-api:latest
   ```
3. Update the image tag in your Helm values
4. Redeploy

## Troubleshooting

### Only 1 Server Showing

**Symptom**: Frontend shows only Stockholm, Sweden

**Cause**: `SERVERS_JSON` is set to test configuration

**Fix**: Follow the "Quick Fix" steps above

### No Servers Loading

**Symptom**: Pod fails to start or logs show "Failed to load servers"

**Cause**: Multiple possible issues:
- SERVERS_JSON has invalid JSON
- SERVERS_FILE_PATH points to non-existent file
- Bundled file is missing from Docker image
- ConfigMap key mismatch

**Fix**:
1. Check pod logs: `kubectl logs -n <namespace> <pod-name>`
2. Verify ConfigMap: `kubectl get configmap -n <namespace> gluetun-api-config -o yaml`
3. Check if bundled file exists: `kubectl exec -n <namespace> <pod-name> -- ls -la /app/data/`

### Different Server Count Than Expected

**Symptom**: Shows different number of servers than documented

**Cause**: Using an older or newer version of the bundled `servers.json` file, or Mullvad has updated their server list

**Solution**: This is normal. Server counts may vary as Mullvad adds/removes servers. As long as you see 400+ servers across multiple countries, the configuration is correct.

## Related Files

- `/gluetun-k8s/app.py` - Server loading logic
- `/gluetun-k8s/config.py` - Configuration variables
- `/gluetun-k8s/data/servers.json` - Bundled server list
- `/charts/geosnappro/templates/gluetun-api-configmap.yaml` - Kubernetes ConfigMap template
- `/charts/geosnappro/values.yaml` - Default Helm values
- `/charts/geosnappro/values-production.yaml` - Production configuration example
- `/tests/run_kind_e2e.sh` - E2E test script (now fixed to use bundled servers)

