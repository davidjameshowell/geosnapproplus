# GeoSnappro Unified Helm Chart

This unified Helm chart deploys the complete GeoSnappro application stack, including:

- **Screenshot API**: The main screenshot service
- **Gluetun API**: VPN proxy management service
- **Frontend**: Web UI for managing screenshots

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- PersistentVolume provisioner support (if using persistent storage)

## Installation

### Quick Start

```bash
# Install with default values
helm install geosnappro ./charts/geosnappro -n geosnappro --create-namespace

# Install with custom values
helm install geosnappro ./charts/geosnappro -n geosnappro --create-namespace -f custom-values.yaml
```

### Required Configuration

Before deploying, you **must** provide WireGuard credentials for the Gluetun API. You can do this in one of two ways:

#### Option 1: Provide credentials in values file

```yaml
gluetunApi:
  wireguard:
    privateKey: "your-wireguard-private-key"
    addresses: "10.68.50.98/32"
```

#### Option 2: Create secret manually and reference it

```bash
kubectl create secret generic gluetun-wireguard-credentials \
  --from-literal=wireguard-private-key="your-key" \
  --from-literal=wireguard-addresses="10.68.50.98/32" \
  -n geosnappro
```

Then use the default secret name in values:

```yaml
gluetunApi:
  wireguardSecret:
    name: gluetun-wireguard-credentials
```

## Configuration

### Values File Structure

The chart uses a unified values file with three main sections:

```yaml
# Screenshot API Configuration
screenshotApi:
  enabled: true
  replicaCount: 1
  image:
    repository: screenshot-api
    tag: latest
  env:
    LOG_LEVEL: "DEBUG"
    VPN_SHARED_PROXY_IDLE_TTL_SECONDS: "20"

# Gluetun API Configuration
gluetunApi:
  enabled: true
  replicaCount: 1
  config:
    instanceLimit: 2
    logLevel: "DEBUG"
  wireguard:
    privateKey: "..."
    addresses: "..."

# Frontend Configuration
frontend:
  enabled: true
  replicaCount: 1
  mediaVolume:
    enabled: true
    size: 1Gi
```

### Key Configuration Options

#### Screenshot API

| Parameter | Description | Default |
|-----------|-------------|---------|
| `screenshotApi.enabled` | Enable Screenshot API | `true` |
| `screenshotApi.replicaCount` | Number of replicas | `1` |
| `screenshotApi.image.repository` | Image repository | `screenshot-api` |
| `screenshotApi.image.tag` | Image tag | `latest` |
| `screenshotApi.env.LOG_LEVEL` | Logging level | `DEBUG` |
| `screenshotApi.env.VPN_SHARED_PROXY_IDLE_TTL_SECONDS` | VPN proxy idle timeout | `20` |

#### Gluetun API

| Parameter | Description | Default |
|-----------|-------------|---------|
| `gluetunApi.enabled` | Enable Gluetun API | `true` |
| `gluetunApi.replicaCount` | Number of replicas | `1` |
| `gluetunApi.config.instanceLimit` | Maximum VPN instances | `2` |
| `gluetunApi.config.logLevel` | Logging level | `DEBUG` |
| `gluetunApi.wireguard.privateKey` | WireGuard private key | *required* |
| `gluetunApi.wireguard.addresses` | WireGuard addresses | *required* |

#### Frontend

| Parameter | Description | Default |
|-----------|-------------|---------|
| `frontend.enabled` | Enable Frontend | `true` |
| `frontend.replicaCount` | Number of replicas | `1` |
| `frontend.image.repository` | Image repository | `frontend` |
| `frontend.env.DEBUG` | Debug mode | `false` |
| `frontend.mediaVolume.enabled` | Enable persistent media volume | `true` |
| `frontend.mediaVolume.size` | Volume size | `1Gi` |

### Ingress Configuration

To enable ingress for any component:

```yaml
frontend:
  ingress:
    enabled: true
    className: "nginx"
    hosts:
      - host: geosnappro.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: geosnappro-tls
        hosts:
          - geosnappro.example.com
```

### Resource Limits

Configure resource limits for each component:

```yaml
screenshotApi:
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 500m
      memory: 512Mi
```

## Upgrading

```bash
helm upgrade geosnappro ./charts/geosnappro -n geosnappro
```

## Uninstalling

```bash
helm uninstall geosnappro -n geosnappro
```

**Note**: This will not delete PersistentVolumeClaims. To delete them:

```bash
kubectl delete pvc -n geosnappro -l app.kubernetes.io/instance=geosnappro
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n geosnappro -l app.kubernetes.io/instance=geosnappro
```

### View Logs

```bash
# Screenshot API logs
kubectl logs -n geosnappro -l app.kubernetes.io/component=screenshot-api

# Gluetun API logs
kubectl logs -n geosnappro -l app.kubernetes.io/component=gluetun-api

# Frontend logs
kubectl logs -n geosnappro -l app.kubernetes.io/component=frontend
```

### Common Issues

1. **Gluetun API not starting**: Ensure WireGuard credentials are correctly configured
2. **Screenshot API can't connect to Gluetun**: Check service names match in configuration
3. **Frontend can't access backends**: Verify service URLs in frontend.env section

## Migration from Separate Charts

If you were previously using separate charts for each component, you can migrate by:

1. Export your current values:
   ```bash
   helm get values screenshot-api > screenshot-values.yaml
   helm get values gluetun-api > gluetun-values.yaml
   helm get values frontend > frontend-values.yaml
   ```

2. Merge them into a unified values file with proper prefixes:
   - `screenshotApi.*`
   - `gluetunApi.*`
   - `frontend.*`

3. Uninstall old charts:
   ```bash
   helm uninstall screenshot-api
   helm uninstall gluetun-api
   helm uninstall frontend
   ```

4. Install unified chart:
   ```bash
   helm install geosnappro ./charts/geosnappro -f unified-values.yaml
   ```

## Values from docker-compose.yml

This chart replicates all configuration from `docker-compose.yml` to ensure parity between Docker Compose and Kubernetes deployments:

### Screenshot API Mapping

| docker-compose.yml | Helm Chart | Notes |
|-------------------|------------|-------|
| `ports: 8000:8000` | `screenshotApi.service.port: 8000` | ClusterIP service by default |
| `PYTHONUNBUFFERED=1` | `screenshotApi.env.PYTHONUNBUFFERED: "1"` | Enabled by default |
| `LOG_LEVEL=DEBUG` | `screenshotApi.env.LOG_LEVEL: "DEBUG"` | Default debug level |
| `GLUETUN_API_URL=http://gluetun-api:8001` | Auto-generated from `screenshotApi.gluetunApi.serviceName` | Automatically configured |
| `VPN_SHARED_PROXY_IDLE_TTL_SECONDS=20` | `screenshotApi.env.VPN_SHARED_PROXY_IDLE_TTL_SECONDS: "20"` | Default 20 seconds |

### Gluetun API Mapping

| docker-compose.yml | Helm Chart | Notes |
|-------------------|------------|-------|
| `ports: 8001:8001` | `gluetunApi.service.port: 8001` | ClusterIP service by default |
| `PYTHONUNBUFFERED=1` | `gluetunApi.config.pythonUnbuffered: "1"` | Enabled by default |
| `LOG_LEVEL=DEBUG` | `gluetunApi.config.logLevel: "DEBUG"` | Default debug level |
| `INSTANCE_LIMIT=2` | `gluetunApi.config.instanceLimit: 2` | Default 2 instances |
| `WIREGUARD_PRIVATE_KEY` | `gluetunApi.wireguard.privateKey` | **Required** - must be set |
| `WIREGUARD_ADDRESSES` | `gluetunApi.wireguard.addresses` | **Required** - must be set |
| `DOCKER_NETWORK=geosnappro-network` | N/A - uses Kubernetes service discovery | Replaced by K8S_NAMESPACE |
| `/var/run/docker.sock` volume | N/A - uses Kubernetes API with RBAC | Pod management via K8s API |

### Frontend Mapping

| docker-compose.yml | Helm Chart | Notes |
|-------------------|------------|-------|
| `ports: 5000:5000` | `frontend.service.port: 5000` | ClusterIP service by default |
| `BACKEND_URL=http://screenshot-api:8000` | `frontend.env.BACKEND_URL` | Auto-configured to match service |
| `BACKEND_WS_PUBLIC_URL=ws://localhost:8000` | `frontend.env.BACKEND_WS_PUBLIC_URL` | May need ingress adjustment |
| `GLUETUN_API_URL=http://gluetun-api:8001` | `frontend.env.GLUETUN_API_URL` | Auto-configured to match service |
| `DEBUG=false` | `frontend.env.DEBUG: "false"` | Default production mode |
| `PORT=5000` | `frontend.env.PORT: "5000"` | Container port |
| `POLL_INTERVAL_SECONDS=2` | `frontend.env.POLL_INTERVAL_SECONDS: "2"` | Default 2 seconds |
| `MEDIA_DIR=/app/media` | `frontend.env.MEDIA_DIR: "/app/media"` | Container mount path |
| `frontend_media` volume | `frontend.mediaVolume` | Persistent volume claim |

### Key Differences

**Docker Compose** uses Docker networking and socket mounting for container orchestration.  
**Kubernetes** uses native service discovery and the Kubernetes API with proper RBAC for pod management.

## Support

For issues and questions:
- GitHub: https://github.com/geosnappro/geosnappro
- Documentation: https://github.com/geosnappro/geosnappro/docs

