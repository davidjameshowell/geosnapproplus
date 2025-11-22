# Gluetun Kubernetes API - Quick Start

Get up and running with Gluetun Kubernetes API in under 5 minutes!

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installed
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) installed
- Valid Mullvad WireGuard credentials

## Step-by-Step Setup

### 1. Get Your WireGuard Credentials

1. Log in to [Mullvad](https://mullvad.net/)
2. Navigate to WireGuard configuration
3. Generate or select a key
4. Note your **Private Key** and **IP Address**

### 2. Clone and Navigate

```bash
cd /path/to/geosnappro-thefinal/gluetun-k8s
```

### 3. Create kind Cluster

```bash
./scripts/setup-kind-cluster.sh
```

**Output:**
```
Creating cluster "gluetun-test" ...
...
Cluster is ready!
```

### 4. Build and Load Docker Image

```bash
./scripts/build-and-load.sh
```

**Output:**
```
Building Docker image...
Loading image into kind cluster...
Image successfully loaded!
```

### 5. Set Credentials and Deploy

```bash
export WIREGUARD_PRIVATE_KEY="paste-your-private-key-here"
export WIREGUARD_ADDRESSES="10.x.x.x/32"

./scripts/deploy.sh
```

**Output:**
```
Deploying Gluetun K8s API to Kubernetes...
Creating namespace...
Creating secret...
...
Deployment complete!
```

### 6. Wait for Pod to be Ready

```bash
kubectl get pods -n gluetun-system -w
```

Wait until you see:
```
NAME                              READY   STATUS    RESTARTS   AGE
gluetun-k8s-api-xxxxxxxxxx-xxxxx  1/1     Running   0          30s
```

Press `Ctrl+C` to exit.

### 7. Test the API

```bash
# Health check
curl http://localhost:30801/health

# Expected: {"status":"healthy","servers_loaded":true}
```

```bash
# Get number of available servers
curl -s http://localhost:30801/servers | jq '. | length'

# Expected: 150 (or similar number)
```

```bash
# Start a VPN pod in USA
curl -X POST http://localhost:30801/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA"}' | jq
```

**Expected Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "proxy": "http://abc123:xyz789@10.244.0.5:8888",
  "pod_name": "gluetun-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "pod_ip": "10.244.0.5"
}
```

### 8. Verify VPN Pod Running

```bash
kubectl get pods -n gluetun-system -l managed-by=gluetun-k8s-api
```

**Expected:**
```
NAME                                                 READY   STATUS    RESTARTS   AGE
gluetun-a1b2c3d4-e5f6-7890-abcd-ef1234567890        1/1     Running   0          45s
```

### 9. Run Automated Tests

```bash
./scripts/test.sh
```

**Expected:**
```
Running test suite...
===== test session starts =====
...
===== X passed in Y seconds =====
Tests complete!
```

## Next Steps

### Use the Proxy

The proxy URL returned in step 7 can be used from any pod in your cluster:

```bash
# Create a test pod
kubectl run -it --rm test-curl --image=curlimages/curl -n gluetun-system -- sh

# Inside the pod:
curl -x http://abc123:xyz789@10.244.0.5:8888 http://ifconfig.me
```

### Check Status

```bash
curl http://localhost:30801/status | jq
```

### Destroy a VPN Pod

```bash
# Get the pod ID from status or start response
POD_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"

curl -X POST http://localhost:30801/destroy \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$POD_ID\"}" | jq
```

### Browse Available Locations

```bash
curl http://localhost:30801/locations | jq '.countries[] | {name: .name, cities: .city_count}'
```

### Filter Servers by Location

```bash
# USA servers
curl "http://localhost:30801/servers?country=USA" | jq '. | length'

# New York servers
curl "http://localhost:30801/servers?city=New+York" | jq
```

## Common Commands

### View Logs

```bash
# API server logs
kubectl logs -n gluetun-system -l app=gluetun-k8s-api -f

# Gluetun VPN pod logs
kubectl logs -n gluetun-system POD_NAME -f
```

### Port Forward (alternative to NodePort)

```bash
kubectl port-forward -n gluetun-system svc/gluetun-k8s-api 8001:8001
# Then access at http://localhost:8001
```

### Restart API Server

```bash
kubectl rollout restart deployment -n gluetun-system gluetun-k8s-api
```

### Delete All VPN Pods

```bash
kubectl delete pods -n gluetun-system -l managed-by=gluetun-k8s-api
```

## Cleanup

When you're done testing:

```bash
# Remove the deployment
./scripts/undeploy.sh

# Delete the kind cluster
kind delete cluster --name gluetun-test
```

## Troubleshooting

### API Not Responding

```bash
# Check pod status
kubectl get pods -n gluetun-system

# Check logs
kubectl logs -n gluetun-system -l app=gluetun-k8s-api --tail=50

# Check service
kubectl get svc -n gluetun-system
```

### VPN Pod Not Starting

```bash
# Check pod events
kubectl describe pod -n gluetun-system POD_NAME

# Check pod logs
kubectl logs -n gluetun-system POD_NAME
```

### Connection Refused

Make sure your kind cluster was created with the port mapping:

```bash
docker ps | grep gluetun-test
# Should show: 0.0.0.0:30801->30801/tcp
```

If not, recreate the cluster:

```bash
kind delete cluster --name gluetun-test
./scripts/setup-kind-cluster.sh
```

## Full Documentation

- [README.md](README.md) - Complete documentation and API reference
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Detailed deployment instructions for different environments

## API Reference Card

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/servers` | GET | List available servers |
| `/locations` | GET | List locations by country/city |
| `/start` | POST | Start a VPN pod |
| `/status` | GET | Get status of running pods |
| `/destroy` | POST | Destroy a VPN pod |
| `/servers/refresh` | POST | Refresh server cache |

## Support

For issues:
1. Check logs: `kubectl logs -n gluetun-system -l app=gluetun-k8s-api`
2. Check events: `kubectl get events -n gluetun-system`
3. Review [Troubleshooting](#troubleshooting) section
4. See full [README](README.md) for detailed help

---

**Happy VPN pod provisioning!** 🚀

