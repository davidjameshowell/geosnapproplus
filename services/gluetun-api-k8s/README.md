# Gluetun Kubernetes API

A Kubernetes-native implementation for provisioning and managing Gluetun VPN containers as Kubernetes pods. This reference implementation leverages the Kubernetes API to provide on-demand VPN proxy services within a Kubernetes cluster.

## Overview

This implementation provides a REST API for managing Gluetun VPN containers as Kubernetes pods, offering:

- **Kubernetes-native architecture**: Uses Kubernetes primitives (Pods, Jobs, RBAC) for container management
- **Dynamic pod provisioning**: Create and destroy Gluetun VPN pods on-demand
- **Mullvad VPN integration**: Automatic server list fetching and WireGuard configuration
- **HTTP proxy support**: Each VPN pod provides an authenticated HTTP proxy
- **Instance limits**: Configurable limits to control resource usage
- **Health monitoring**: Built-in health checks for Kubernetes liveness/readiness probes

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Gluetun K8s API Server                 │
│                   (Deployment)                      │
│                                                     │
│  ┌──────────────┐        ┌──────────────────┐     │
│  │  Flask API   │───────▶│  K8s Manager     │     │
│  │   (REST)     │        │  (K8s Client)    │     │
│  └──────────────┘        └──────────────────┘     │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
         ┌──────────────────────────────┐
         │    Kubernetes API Server      │
         └──────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌────────────────┐          ┌────────────────┐
│  Gluetun Pod 1 │          │  Gluetun Pod 2 │
│  (VPN Proxy)   │          │  (VPN Proxy)   │
└────────────────┘          └────────────────┘
```

## Prerequisites

1. **Kubernetes Cluster**: A running Kubernetes cluster (kind, minikube, or production cluster)
   - Minimum version: 1.24+
   - Sufficient resources for VPN pods (each pod: ~256MB RAM, 0.5 CPU)

2. **kubectl**: Configured to access your cluster
   ```bash
   kubectl cluster-info
   ```

3. **Docker**: For building container images
   ```bash
   docker --version
   ```

4. **WireGuard Credentials**: Valid Mullvad WireGuard credentials
   - Private key
   - IP addresses

## Quick Start with kind

### 1. Create a kind cluster

```bash
./scripts/setup-kind-cluster.sh
```

This creates a kind cluster named `gluetun-test` with the API port exposed.

### 2. Build and load the Docker image

```bash
./scripts/build-and-load.sh
```

This builds the Docker image and loads it into the kind cluster.

### 3. Deploy to Kubernetes

```bash
export WIREGUARD_PRIVATE_KEY="your-private-key"
export WIREGUARD_ADDRESSES="10.x.x.x/32"

./scripts/deploy.sh
```

### 4. Verify deployment

```bash
kubectl get pods -n gluetun-system
kubectl logs -n gluetun-system -l app=gluetun-k8s-api -f
```

### 5. Test the API

```bash
# Health check
curl http://localhost:30801/health

# Get server list
curl http://localhost:30801/servers | jq

# Start a VPN pod
curl -X POST http://localhost:30801/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA"}'
```

### 6. Run automated tests

```bash
./scripts/test.sh
```

## API Endpoints

### Health Check

```http
GET /health
```

Returns API health status.

**Response:**
```json
{
  "status": "healthy",
  "servers_loaded": true
}
```

### List Servers

```http
GET /servers?country=USA&city=New+York&force=false
```

Get list of available Mullvad servers with optional filtering.

**Query Parameters:**
- `country` (optional): Filter by country name (case-insensitive, partial match)
- `city` (optional): Filter by city name (case-insensitive, partial match)
- `force` (optional): Force refresh server cache (`true`, `1`, or `yes`)

**Response:**
```json
{
  "usa-new-york-ny-us-nyc-wg-301": {
    "hostname": "us-nyc-wg-301",
    "country": "USA",
    "city": "New York",
    "vpn": "wireguard"
  }
}
```

### Get Locations

```http
GET /locations?force=false
```

Get hierarchical list of locations organized by country and city.

**Response:**
```json
{
  "countries": [
    {
      "name": "USA",
      "city_count": 5,
      "total_servers": 50,
      "cities": [
        {
          "name": "New York",
          "server_count": 10,
          "sample_hostname": "us-nyc-wg-301"
        }
      ]
    }
  ]
}
```

### Start VPN Pod

```http
POST /start
Content-Type: application/json

{
  "server": "usa-new-york-ny-us-nyc-wg-301"
}
```

OR

```http
POST /start
Content-Type: application/json

{
  "country": "USA",
  "city": "New York"
}
```

Start a Gluetun VPN pod with the specified server or location.

**Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "proxy": "http://username:password@10.244.0.5:8888",
  "pod_name": "gluetun-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "pod_ip": "10.244.0.5"
}
```

**Error Responses:**
- `400`: Invalid server or missing parameters
- `429`: Instance limit reached
- `500`: Failed to start pod

### Get Status

```http
GET /status
```

Get status of all running Gluetun pods.

**Response:**
```json
{
  "a1b2c3d4-e5f6-7890-abcd-ef1234567890": {
    "pod_name": "gluetun-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "pod_ip": "10.244.0.5",
    "server": "usa-new-york-ny-us-nyc-wg-301",
    "username": "abc123",
    "password": "xyz789",
    "port": 8888,
    "status": "running"
  }
}
```

### Destroy VPN Pod

```http
POST /destroy
Content-Type: application/json

{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

Destroy a Gluetun VPN pod.

**Response:**
```json
{
  "message": "Pod destroyed"
}
```

**Error Responses:**
- `404`: Pod not found
- `500`: Failed to destroy pod

### Refresh Servers

```http
POST /servers/refresh
```

Force refresh of the Mullvad server cache.

**Response:**
```json
{
  "message": "Server cache refreshed",
  "server_count": 150
}
```

## Configuration

### Environment Variables

The API can be configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `K8S_NAMESPACE` | Namespace for Gluetun pods | `gluetun-system` |
| `INSTANCE_LIMIT` | Maximum concurrent VPN pods | `5` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `SERVERS_FILE_PATH` | Optional path to a pre-generated Mullvad `servers.json` (mounted inside the container) | empty |
| `SERVERS_JSON` | Optional raw JSON string containing Mullvad server data | empty |
| `WIREGUARD_PRIVATE_KEY` | WireGuard private key | Required |
| `WIREGUARD_ADDRESSES` | WireGuard IP addresses | Required |

### Kubernetes Resources

Modify `k8s/03-configmap.yaml` to adjust configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gluetun-k8s-api-config
data:
  K8S_NAMESPACE: "gluetun-system"
  INSTANCE_LIMIT: "10"
  LOG_LEVEL: "DEBUG"
```

### Preloading Mullvad Server List

The container image ships with a trimmed Mullvad server catalogue at `/app/data/servers.json`.
On startup the API automatically loads this bundled list, so no additional Kubernetes resources
are required for most environments.

If you want to supply your own curated list (for example, to refresh the catalogue or restrict
it further), pass it through either:

- `SERVERS_JSON` – raw JSON string, or
- `SERVERS_FILE_PATH` – path to a mounted file (e.g. via ConfigMap or Secret)

The helper script `./scripts/export-servers-json.sh` can generate a fresh list from the upstream
Gluetun image:

```bash
export WIREGUARD_PRIVATE_KEY="your-private-key"
export WIREGUARD_ADDRESSES="10.x.x.x/32"
./scripts/export-servers-json.sh ./servers.json
```

Once you mount or inject the new list, update `SERVERS_FILE_PATH` and restart the deployment.
If a custom list fails to load, the API falls back to the bundled file and, as a last resort,
retries the Kubernetes job-based discovery.

## Development

### Project Structure

```
gluetun-k8s/
├── app.py                  # Flask API server
├── k8s_manager.py          # Kubernetes API manager
├── config.py               # Configuration
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image
├── k8s/                    # Kubernetes manifests
│   ├── 00-namespace.yaml
│   ├── 01-secret.yaml
│   ├── 02-rbac.yaml
│   ├── 03-configmap.yaml
│   ├── 04-deployment.yaml
│   ├── 05-service.yaml
│   └── 06-nodeport-service.yaml
├── scripts/                # Deployment scripts
│   ├── setup-kind-cluster.sh
│   ├── build-and-load.sh
│   ├── deploy.sh
│   ├── undeploy.sh
│   └── test.sh
└── tests/                  # Test suite
    └── test_gluetun_k8s_api.py
```

### Running Locally

To develop locally without deploying to Kubernetes:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export K8S_NAMESPACE=default
export WIREGUARD_PRIVATE_KEY="your-key"
export WIREGUARD_ADDRESSES="10.x.x.x/32"

# Run the API server
python app.py
```

Note: This still requires a Kubernetes cluster as it uses the Kubernetes API to manage pods.

### Testing

Run the test suite:

```bash
# Using the test script
./scripts/test.sh

# Or manually with pytest
pytest tests/ -v

# Run specific test class
pytest tests/test_gluetun_k8s_api.py::TestStartGluetun -v
```

Set a custom API URL for testing:

```bash
export GLUETUN_K8S_API_URL=http://localhost:30801
pytest tests/ -v
```

## Deployment to Production

### 1. Update the Deployment Image

For production, build and push the image to a container registry:

```bash
# Build for production
docker build -t your-registry/gluetun-k8s-api:v1.0.0 .

# Push to registry
docker push your-registry/gluetun-k8s-api:v1.0.0
```

Update `k8s/04-deployment.yaml`:

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          image: your-registry/gluetun-k8s-api:v1.0.0
          imagePullPolicy: Always
```

### 2. Configure Secrets

Create the secret securely:

```bash
kubectl create secret generic gluetun-wireguard-credentials \
  --from-literal=wireguard-private-key="$WIREGUARD_PRIVATE_KEY" \
  --from-literal=wireguard-addresses="$WIREGUARD_ADDRESSES" \
  -n gluetun-system
```

### 3. Apply Resources

```bash
kubectl apply -f k8s/
```

### 4. Expose the Service

For production access, consider using an Ingress instead of NodePort:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gluetun-k8s-api
  namespace: gluetun-system
spec:
  rules:
    - host: gluetun-api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: gluetun-k8s-api
                port:
                  number: 8001
```

## Troubleshooting

### Pods not starting

Check pod logs:
```bash
kubectl logs -n gluetun-system -l app=gluetun-k8s-api
```

Check events:
```bash
kubectl get events -n gluetun-system --sort-by='.lastTimestamp'
```

### API not accessible

Check service status:
```bash
kubectl get svc -n gluetun-system
```

Port-forward for local testing:
```bash
kubectl port-forward -n gluetun-system svc/gluetun-k8s-api 8001:8001
```

### Gluetun pods failing

Check Gluetun pod logs:
```bash
kubectl logs -n gluetun-system -l managed-by=gluetun-k8s-api
```

Verify WireGuard credentials:
```bash
kubectl get secret gluetun-wireguard-credentials -n gluetun-system -o jsonpath='{.data}'
```

### Permission errors

Verify RBAC configuration:
```bash
kubectl auth can-i create pods --namespace=gluetun-system --as=system:serviceaccount:gluetun-system:gluetun-k8s-api
```

## Cleanup

### Remove the deployment

```bash
./scripts/undeploy.sh
```

### Delete the namespace

```bash
kubectl delete namespace gluetun-system
```

### Delete the kind cluster

```bash
kind delete cluster --name gluetun-test
```

## Comparison with Docker Implementation

| Feature | Docker API | Kubernetes API |
|---------|------------|----------------|
| Container Management | Docker API | Kubernetes API |
| Networking | Docker networks | Pod networking |
| Resource Limits | Docker configs | K8s ResourceQuotas |
| Scaling | Manual | K8s native |
| High Availability | External orchestration | Built-in |
| Service Discovery | Manual | K8s Services |
| Health Checks | Manual | Liveness/Readiness probes |
| Deployment | docker-compose | kubectl/Helm |

## Security Considerations

1. **Secrets Management**: WireGuard credentials are stored as Kubernetes Secrets
2. **RBAC**: Minimal permissions granted to service account
3. **Network Policies**: Consider implementing NetworkPolicies to restrict pod communication
4. **Pod Security**: Gluetun pods require NET_ADMIN capability for VPN functionality
5. **API Access**: Consider implementing authentication/authorization for the API

## License

This implementation follows the same license as the main geosnappro project.

## Contributing

Contributions are welcome! Please follow the existing code style and include tests for new features.

## Support

For issues specific to this Kubernetes implementation, please check:
1. This README and troubleshooting section
2. Kubernetes cluster logs and events
3. The main Gluetun documentation: https://github.com/qdm12/gluetun

