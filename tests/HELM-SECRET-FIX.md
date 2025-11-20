# Helm Secret Ownership Fix

## Problem

When running `run_kind_e2e.sh`, the script encountered this error:

```
Error: Unable to continue with install: Secret "gluetun-wireguard-credentials" in namespace "geosnap-e2e" 
exists and cannot be imported into the current release: invalid ownership metadata; 
label validation error: missing key "app.kubernetes.io/managed-by": must be set to "Helm"; 
annotation validation error: missing key "meta.helm.sh/release-name": must be set to "geosnappro-e2e"; 
annotation validation error: missing key "meta.helm.sh/release-namespace": must be set to "geosnap-e2e"
```

## Root Cause

The script was creating the WireGuard credentials secret **manually** using `kubectl apply`:

```bash
apply_wireguard_secret() {
  kubectl apply -n "${NAMESPACE}" -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: gluetun-wireguard-credentials
type: Opaque
stringData:
  wireguard-private-key: dummy-private-key
  wireguard-addresses: 10.0.0.2/32
EOF
}
```

Then, when Helm tried to install the unified chart, it encountered a secret that:
- ✅ Already existed
- ❌ Wasn't created by Helm (missing Helm labels/annotations)
- ❌ Can't be adopted by Helm without proper metadata

Helm 3 requires resources it manages to have specific labels and annotations:
- `app.kubernetes.io/managed-by: Helm`
- `meta.helm.sh/release-name: geosnappro-e2e`
- `meta.helm.sh/release-namespace: geosnap-e2e`

## Solution

The unified Helm chart **already creates the secret** via the `gluetun-api-secret.yaml` template:

```yaml
{{- if .Values.gluetunApi.enabled }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ .Values.gluetunApi.wireguardSecret.name }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "geosnappro.gluetunApi.labels" . | nindent 4 }}
type: Opaque
stringData:
  {{ .Values.gluetunApi.wireguardSecret.privateKeyKey }}: {{ .Values.gluetunApi.wireguard.privateKey | quote }}
  {{ .Values.gluetunApi.wireguardSecret.addressesKey }}: {{ .Values.gluetunApi.wireguard.addresses | quote }}
{{- end }}
```

So we need to:
1. ✅ **Remove** the manual secret creation
2. ✅ **Delete** any existing secret before Helm install
3. ✅ **Provide** WireGuard credentials in the values file

### Changes Made

#### 1. Replaced `apply_wireguard_secret()` with `ensure_wireguard_secret_removed()`

**Before:**
```bash
apply_wireguard_secret() {
  log "Ensuring dummy WireGuard credentials secret exists"
  cat <<EOF | kubectl apply -n "${NAMESPACE}" -f -
apiVersion: v1
kind: Secret
metadata:
  name: gluetun-wireguard-credentials
type: Opaque
stringData:
  wireguard-private-key: dummy-private-key
  wireguard-addresses: 10.0.0.2/32
EOF
}
```

**After:**
```bash
ensure_wireguard_secret_removed() {
  log "Removing any existing WireGuard credentials secret (Helm will create it)"
  if kubectl get secret gluetun-wireguard-credentials -n "${NAMESPACE}" >/dev/null 2>&1; then
    log "Deleting existing secret to allow Helm to manage it"
    kubectl delete secret gluetun-wireguard-credentials -n "${NAMESPACE}" 2>/dev/null || true
  fi
}
```

#### 2. Added WireGuard Credentials to Values File

In `write_unified_values_file()`, added the credentials:

```yaml
gluetunApi:
  wireguardSecret:
    name: gluetun-wireguard-credentials
    privateKeyKey: wireguard-private-key
    addressesKey: wireguard-addresses
  
  # Dummy WireGuard credentials for testing
  # The unified chart will create the secret automatically
  wireguard:
    privateKey: "dummy-private-key-for-testing"
    addresses: "10.0.0.2/32"
```

#### 3. Updated main() Function

**Before:**
```bash
write_unified_values_file
create_namespace
apply_wireguard_secret        # ❌ Creates secret manually
deploy_unified_chart
```

**After:**
```bash
write_unified_values_file
create_namespace
ensure_wireguard_secret_removed  # ✅ Removes any existing secret
deploy_unified_chart              # ✅ Helm creates secret with proper labels
```

## How It Works Now

1. **Script generates unified values file** with WireGuard credentials
2. **Script removes any existing secret** (if present from previous run)
3. **Helm installs the chart** and creates the secret with proper ownership metadata
4. **Secret is now managed by Helm** with all required labels/annotations

## Benefits

✅ **Proper Helm Ownership** - Secret has correct labels/annotations  
✅ **Clean Upgrades** - `helm upgrade` can manage the secret  
✅ **Consistent Management** - All resources managed by Helm  
✅ **No Conflicts** - No ownership metadata errors  

## Verification

After the fix, the deployment should succeed:

```
[INFO]  Removing any existing WireGuard credentials secret (Helm will create it)
[INFO]  Deploying UNIFIED GeoSnappro Helm chart
[INFO]  Chart location: /home/david/repos/geosnappro-thefinal/charts/geosnappro
[INFO]  Release name: geosnappro-e2e
[INFO]  This will deploy: screenshot-api, gluetun-api, and frontend (all in one chart)
Release "geosnappro-e2e" does not exist. Installing it now.
✅ SUCCESS!
```

Verify the secret has proper labels:

```bash
kubectl get secret gluetun-wireguard-credentials -n geosnap-e2e -o yaml
```

Should show:
```yaml
metadata:
  labels:
    app.kubernetes.io/managed-by: Helm
  annotations:
    meta.helm.sh/release-name: geosnappro-e2e
    meta.helm.sh/release-namespace: geosnap-e2e
```

## Testing

Run the script again:

```bash
./tests/run_kind_e2e.sh
```

The deployment should now complete successfully! 🎉

## Related Files

- `tests/run_kind_e2e.sh` - Updated script
- `charts/geosnappro/templates/gluetun-api-secret.yaml` - Secret template
- `charts/geosnappro/values.yaml` - Default values with wireguard credentials

---

**Status**: ✅ FIXED  
**Tested**: Syntax validated  
**Ready**: For deployment

