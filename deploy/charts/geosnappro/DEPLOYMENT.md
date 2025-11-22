# GeoSnappro Unified Chart - Deployment Guide

This guide provides step-by-step instructions for deploying the GeoSnappro application using the unified Helm chart.

## Overview

The GeoSnappro unified Helm chart deploys a complete application stack consisting of:

- **Screenshot API** (Port 8000): Main screenshot service with VPN integration
- **Gluetun API** (Port 8001): VPN proxy management service for managing Gluetun instances
- **Frontend** (Port 5000): Web interface for screenshot management

All three services are deployed with a single `helm install` command, ensuring consistent configuration and simplified management.

## Prerequisites

### Required

1. **Kubernetes Cluster** (v1.19+)
   - Minikube, Kind, K3s, or cloud-managed cluster (GKE, EKS, AKS)
   - Access configured via `kubectl`

2. **Helm** (v3.0+)
   ```bash
   # Verify Helm installation
   helm version
   ```

3. **WireGuard Credentials**
   - Private key from your VPN provider (Mullvad, ProtonVPN, etc.)
   - WireGuard addresses (CIDR notation, e.g., `10.68.50.98/32`)

### Optional

- **Ingress Controller** (for external access)
  - NGINX Ingress Controller
  - Traefik
  - HAProxy Ingress

- **cert-manager** (for TLS certificates)
- **Persistent Volume Provisioner** (for media storage)

## Quick Start (Development)

Deploy the application with default settings:

```bash
# Clone repository (if not already done)
cd /home/david/repos/geosnappro-thefinal

# Create namespace
kubectl create namespace geosnappro

# Deploy with default values (includes example WireGuard credentials)
helm install geosnappro ./charts/geosnappro \
  --namespace geosnappro \
  --create-namespace

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=geosnappro -n geosnappro --timeout=300s

# Port forward to access frontend
kubectl port-forward svc/geosnappro-frontend 5000:5000 -n geosnappro
```

Visit http://localhost:5000 to access the application.

## Production Deployment

### Step 1: Prepare WireGuard Credentials

Create a Kubernetes secret with your WireGuard credentials:

```bash
kubectl create secret generic gluetun-wireguard-credentials \
  --from-literal=wireguard-private-key="YOUR_PRIVATE_KEY_HERE" \
  --from-literal=wireguard-addresses="YOUR_ADDRESSES_HERE" \
  --namespace geosnappro
```

### Step 2: Create Custom Values File

Create a `custom-values.yaml` file:

```yaml
# custom-values.yaml
global:
  imagePullSecrets: []

# Screenshot API Configuration
screenshotApi:
  enabled: true
  replicaCount: 2
  
  image:
    repository: your-registry.example.com/screenshot-api
    tag: "1.0.0"
    pullPolicy: IfNotPresent
  
  resources:
    limits:
      cpu: 2000m
      memory: 2Gi
    requests:
      cpu: 1000m
      memory: 1Gi
  
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
  
  env:
    LOG_LEVEL: "INFO"
    VPN_SHARED_PROXY_IDLE_TTL_SECONDS: "300"
  
  ingress:
    enabled: true
    className: "nginx"
    annotations:
      cert-manager.io/cluster-issuer: "letsencrypt-prod"
    hosts:
      - host: api.geosnappro.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: screenshot-api-tls
        hosts:
          - api.geosnappro.example.com

# Gluetun API Configuration
gluetunApi:
  enabled: true
  replicaCount: 1
  
  image:
    repository: your-registry.example.com/gluetun-k8s-api
    tag: "1.0.0"
    pullPolicy: IfNotPresent
  
  config:
    instanceLimit: 10
    logLevel: "INFO"
    pythonUnbuffered: "1"
  
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 500m
      memory: 512Mi
  
  # Use the secret created in Step 1
  wireguardSecret:
    name: "gluetun-wireguard-credentials"

# Frontend Configuration
frontend:
  enabled: true
  replicaCount: 2
  
  image:
    repository: your-registry.example.com/frontend
    tag: "1.0.0"
    pullPolicy: IfNotPresent
  
  resources:
    limits:
      cpu: 500m
      memory: 512Mi
    requests:
      cpu: 250m
      memory: 256Mi
  
  env:
    DEBUG: "false"
    POLL_INTERVAL_SECONDS: "5"
    BACKEND_WS_PUBLIC_URL: "wss://geosnappro.example.com/ws"
  
  mediaVolume:
    enabled: true
    storageClass: "fast-ssd"
    size: 20Gi
  
  ingress:
    enabled: true
    className: "nginx"
    annotations:
      cert-manager.io/cluster-issuer: "letsencrypt-prod"
    hosts:
      - host: geosnappro.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: frontend-tls
        hosts:
          - geosnappro.example.com
```

### Step 3: Deploy the Chart

```bash
# Install the chart
helm install geosnappro ./charts/geosnappro \
  --namespace geosnappro \
  --create-namespace \
  --values custom-values.yaml

# Monitor deployment
kubectl get pods -n geosnappro -w
```

### Step 4: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n geosnappro -l app.kubernetes.io/instance=geosnappro

# Check services
kubectl get svc -n geosnappro

# Check ingress (if enabled)
kubectl get ingress -n geosnappro

# View logs
kubectl logs -n geosnappro -l app.kubernetes.io/component=screenshot-api --tail=50
kubectl logs -n geosnappro -l app.kubernetes.io/component=gluetun-api --tail=50
kubectl logs -n geosnappro -l app.kubernetes.io/component=frontend --tail=50
```

## Configuration Reference

### Docker Compose to Helm Migration

All settings from `docker-compose.yml` are replicated in the Helm chart:

| Component | Docker Compose Setting | Helm Chart Path | Default Value |
|-----------|----------------------|-----------------|---------------|
| Screenshot API | `ports: 8000:8000` | `screenshotApi.service.port` | `8000` |
| Screenshot API | `PYTHONUNBUFFERED=1` | `screenshotApi.env.PYTHONUNBUFFERED` | `"1"` |
| Screenshot API | `LOG_LEVEL=DEBUG` | `screenshotApi.env.LOG_LEVEL` | `"DEBUG"` |
| Screenshot API | `VPN_SHARED_PROXY_IDLE_TTL_SECONDS=20` | `screenshotApi.env.VPN_SHARED_PROXY_IDLE_TTL_SECONDS` | `"20"` |
| Gluetun API | `ports: 8001:8001` | `gluetunApi.service.port` | `8001` |
| Gluetun API | `PYTHONUNBUFFERED=1` | `gluetunApi.config.pythonUnbuffered` | `"1"` |
| Gluetun API | `LOG_LEVEL=DEBUG` | `gluetunApi.config.logLevel` | `"DEBUG"` |
| Gluetun API | `INSTANCE_LIMIT=2` | `gluetunApi.config.instanceLimit` | `2` |
| Gluetun API | `WIREGUARD_PRIVATE_KEY` | `gluetunApi.wireguard.privateKey` | *required* |
| Gluetun API | `WIREGUARD_ADDRESSES` | `gluetunApi.wireguard.addresses` | *required* |
| Frontend | `ports: 5000:5000` | `frontend.service.port` | `5000` |
| Frontend | `DEBUG=false` | `frontend.env.DEBUG` | `"false"` |
| Frontend | `POLL_INTERVAL_SECONDS=2` | `frontend.env.POLL_INTERVAL_SECONDS` | `"2"` |
| Frontend | `MEDIA_DIR=/app/media` | `frontend.env.MEDIA_DIR` | `"/app/media"` |
| Frontend | `frontend_media` volume | `frontend.mediaVolume.*` | 1Gi PVC |

### Environment Variables

All environment variables from `docker-compose.yml` are preserved:

#### Screenshot API
- `PYTHONUNBUFFERED=1` - Python output buffering
- `LOG_LEVEL=DEBUG` - Logging verbosity
- `GLUETUN_API_URL` - Auto-configured from service discovery
- `VPN_SHARED_PROXY_IDLE_TTL_SECONDS=20` - VPN proxy timeout

#### Gluetun API
- `PYTHONUNBUFFERED=1` - Python output buffering
- `LOG_LEVEL=DEBUG` - Logging verbosity
- `INSTANCE_LIMIT=2` - Maximum concurrent VPN instances
- `K8S_NAMESPACE` - Auto-configured from release namespace
- `WIREGUARD_PRIVATE_KEY` - From secret
- `WIREGUARD_ADDRESSES` - From secret

#### Frontend
- `BACKEND_URL=http://screenshot-api:8000` - Screenshot API endpoint
- `BACKEND_WS_PUBLIC_URL=ws://localhost:8000` - WebSocket endpoint (adjust for ingress)
- `GLUETUN_API_URL=http://gluetun-api:8001` - Gluetun API endpoint
- `DEBUG=false` - Debug mode
- `PORT=5000` - Server port
- `POLL_INTERVAL_SECONDS=2` - Polling interval
- `MEDIA_DIR=/app/media` - Media storage path

## Networking

### Service Discovery

Services communicate using Kubernetes DNS:

```
screenshot-api:8000       # Screenshot API service
gluetun-api:8001         # Gluetun API service  
frontend:5000            # Frontend service
```

These are automatically configured in the environment variables.

### External Access

#### Option 1: Port Forwarding (Development)

```bash
# Frontend
kubectl port-forward svc/geosnappro-frontend 5000:5000 -n geosnappro

# Screenshot API
kubectl port-forward svc/geosnappro-screenshot-api 8000:8000 -n geosnappro

# Gluetun API
kubectl port-forward svc/geosnappro-gluetun-api 8001:8001 -n geosnappro
```

#### Option 2: NodePort Service (Testing)

Enable NodePort for any service:

```yaml
gluetunApi:
  nodePortService:
    enabled: true
    port: 8001
    nodePort: 30801
```

#### Option 3: Ingress (Production)

Enable ingress with TLS:

```yaml
frontend:
  ingress:
    enabled: true
    className: "nginx"
    annotations:
      cert-manager.io/cluster-issuer: "letsencrypt-prod"
      nginx.ingress.kubernetes.io/ssl-redirect: "true"
    hosts:
      - host: geosnappro.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: frontend-tls
        hosts:
          - geosnappro.example.com
```

## Storage

### Frontend Media Volume

The frontend requires persistent storage for media files:

```yaml
frontend:
  mediaVolume:
    enabled: true
    storageClass: "standard"  # Use your cluster's storage class
    accessMode: ReadWriteOnce
    size: 1Gi
    mountPath: "/app/media"
```

Common storage classes:
- `standard` - Default
- `fast-ssd` - SSD storage
- `gp2` - AWS EBS
- `pd-standard` - GCP Persistent Disk

Check available storage classes:

```bash
kubectl get storageclass
```

## Scaling

### Manual Scaling

```bash
# Scale screenshot API
kubectl scale deployment geosnappro-screenshot-api -n geosnappro --replicas=3

# Scale frontend
kubectl scale deployment geosnappro-frontend -n geosnappro --replicas=2
```

### Horizontal Pod Autoscaling (HPA)

Enable autoscaling in values:

```yaml
screenshotApi:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
    targetMemoryUtilizationPercentage: 80
```

Check HPA status:

```bash
kubectl get hpa -n geosnappro
```

## Upgrading

### Upgrade Chart

```bash
# Update values
helm upgrade geosnappro ./charts/geosnappro \
  --namespace geosnappro \
  --values custom-values.yaml

# Or upgrade with inline values
helm upgrade geosnappro ./charts/geosnappro \
  --namespace geosnappro \
  --set screenshotApi.image.tag=1.1.0
```

### View Release History

```bash
helm history geosnappro -n geosnappro
```

### Rollback

```bash
# Rollback to previous version
helm rollback geosnappro -n geosnappro

# Rollback to specific revision
helm rollback geosnappro 2 -n geosnappro
```

## Monitoring and Troubleshooting

### Check Pod Status

```bash
# All pods
kubectl get pods -n geosnappro -l app.kubernetes.io/instance=geosnappro

# Specific component
kubectl get pods -n geosnappro -l app.kubernetes.io/component=screenshot-api
kubectl get pods -n geosnappro -l app.kubernetes.io/component=gluetun-api
kubectl get pods -n geosnappro -l app.kubernetes.io/component=frontend
```

### View Logs

```bash
# All containers
kubectl logs -n geosnappro -l app.kubernetes.io/instance=geosnappro --all-containers=true

# Specific component
kubectl logs -n geosnappro -l app.kubernetes.io/component=screenshot-api --tail=100 -f
kubectl logs -n geosnappro -l app.kubernetes.io/component=gluetun-api --tail=100 -f
kubectl logs -n geosnappro -l app.kubernetes.io/component=frontend --tail=100 -f
```

### Describe Resources

```bash
# Pods
kubectl describe pod <pod-name> -n geosnappro

# Services
kubectl describe svc geosnappro-screenshot-api -n geosnappro

# Ingress
kubectl describe ingress -n geosnappro
```

### Common Issues

#### 1. Gluetun API Pods Not Starting

**Symptom**: Gluetun API pod stuck in `CrashLoopBackOff`

**Possible Causes**:
- Invalid WireGuard credentials
- Missing RBAC permissions
- Insufficient resources

**Solution**:
```bash
# Check logs
kubectl logs -n geosnappro -l app.kubernetes.io/component=gluetun-api

# Verify secret exists
kubectl get secret gluetun-wireguard-credentials -n geosnappro

# Check RBAC
kubectl get role,rolebinding -n geosnappro
```

#### 2. Screenshot API Can't Connect to Gluetun API

**Symptom**: Screenshot API logs show connection errors to Gluetun API

**Solution**:
```bash
# Verify Gluetun API service
kubectl get svc geosnappro-gluetun-api -n geosnappro

# Test connectivity from screenshot-api pod
kubectl exec -it <screenshot-api-pod> -n geosnappro -- curl http://gluetun-api:8001/health
```

#### 3. Frontend Can't Access Backend

**Symptom**: Frontend shows connection errors

**Solution**:
```bash
# Check service endpoints
kubectl get endpoints -n geosnappro

# Verify environment variables
kubectl exec -it <frontend-pod> -n geosnappro -- env | grep BACKEND_URL
```

#### 4. PVC Not Binding

**Symptom**: Frontend pod stuck in `Pending` state

**Solution**:
```bash
# Check PVC status
kubectl get pvc -n geosnappro

# Check storage class
kubectl get storageclass

# Describe PVC for events
kubectl describe pvc geosnappro-frontend-media -n geosnappro
```

### Health Checks

All services expose health endpoints:

```bash
# Port forward and test
kubectl port-forward svc/geosnappro-screenshot-api 8000:8000 -n geosnappro
curl http://localhost:8000/health

kubectl port-forward svc/geosnappro-gluetun-api 8001:8001 -n geosnappro
curl http://localhost:8001/health

kubectl port-forward svc/geosnappro-frontend 5000:5000 -n geosnappro
curl http://localhost:5000/
```

## Uninstalling

### Remove the Application

```bash
# Uninstall the Helm release
helm uninstall geosnappro -n geosnappro
```

**Note**: This does NOT delete:
- PersistentVolumeClaims (PVCs)
- Secrets (if manually created)

### Delete PVCs

```bash
# List PVCs
kubectl get pvc -n geosnappro

# Delete PVCs
kubectl delete pvc -n geosnappro -l app.kubernetes.io/instance=geosnappro
```

### Delete Namespace

```bash
# This will delete everything in the namespace
kubectl delete namespace geosnappro
```

## Advanced Configuration

### Custom Service Names

Override default service names:

```yaml
screenshotApi:
  fullnameOverride: "my-screenshot-api"
  
gluetunApi:
  fullnameOverride: "my-gluetun-api"
  
frontend:
  fullnameOverride: "my-frontend"
```

### Disable Components

Run only specific components:

```yaml
screenshotApi:
  enabled: true
  
gluetunApi:
  enabled: true
  
frontend:
  enabled: false  # Don't deploy frontend
```

### Multiple Environments

Use different values files for each environment:

```bash
# Development
helm install geosnappro ./charts/geosnappro \
  -n geosnappro-dev \
  --values values-dev.yaml

# Staging
helm install geosnappro ./charts/geosnappro \
  -n geosnappro-staging \
  --values values-staging.yaml

# Production
helm install geosnappro ./charts/geosnappro \
  -n geosnappro-prod \
  --values values-production.yaml
```

## Support and Resources

- **Documentation**: See `README.md` in the charts directory
- **Issues**: Report at https://github.com/geosnappro/geosnappro/issues
- **Values Reference**: Check `values.yaml` for all available options
- **Production Example**: See `values-production.yaml`

## Summary

The unified GeoSnappro Helm chart provides:

✅ **Single Deployment** - All services in one chart  
✅ **Configuration Parity** - Matches docker-compose.yml  
✅ **Production Ready** - Autoscaling, ingress, TLS support  
✅ **Easy Upgrades** - Helm-managed releases  
✅ **Flexible Configuration** - Enable/disable components as needed  

Happy deploying! 🚀

