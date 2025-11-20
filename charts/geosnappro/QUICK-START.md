# GeoSnappro Unified Chart - Quick Start

## 🚀 Deploy in 3 Steps

### Step 1: Create Namespace

```bash
kubectl create namespace geosnappro
```

### Step 2: Create WireGuard Secret

```bash
kubectl create secret generic gluetun-wireguard-credentials \
  --from-literal=wireguard-private-key="YOUR_WIREGUARD_PRIVATE_KEY" \
  --from-literal=wireguard-addresses="YOUR_WIREGUARD_ADDRESSES" \
  --namespace geosnappro
```

### Step 3: Deploy Chart

```bash
cd /home/david/repos/geosnappro-thefinal

helm install geosnappro ./charts/geosnappro \
  --namespace geosnappro
```

## ✅ Verify Deployment

```bash
# Check pods
kubectl get pods -n geosnappro

# Check services
kubectl get svc -n geosnappro

# View logs
kubectl logs -n geosnappro -l app.kubernetes.io/instance=geosnappro --all-containers=true
```

## 🌐 Access Application

### Development (Port Forward)

```bash
kubectl port-forward svc/geosnappro-frontend 5000:5000 -n geosnappro
```

Visit: **http://localhost:5000**

### Production (Ingress)

Create custom values file:

```yaml
# custom-values.yaml
frontend:
  ingress:
    enabled: true
    className: "nginx"
    hosts:
      - host: geosnappro.example.com
        paths:
          - path: /
            pathType: Prefix
```

Deploy with custom values:

```bash
helm install geosnappro ./charts/geosnappro \
  --namespace geosnappro \
  --values custom-values.yaml
```

## 📊 What Gets Deployed

| Component | Port | Description |
|-----------|------|-------------|
| **Screenshot API** | 8000 | Main screenshot service with VPN integration |
| **Gluetun API** | 8001 | VPN proxy management service |
| **Frontend** | 5000 | Web interface for screenshots |

## 🔧 Common Commands

### View Status

```bash
kubectl get all -n geosnappro -l app.kubernetes.io/instance=geosnappro
```

### View Logs

```bash
# Screenshot API
kubectl logs -n geosnappro -l app.kubernetes.io/component=screenshot-api -f

# Gluetun API
kubectl logs -n geosnappro -l app.kubernetes.io/component=gluetun-api -f

# Frontend
kubectl logs -n geosnappro -l app.kubernetes.io/component=frontend -f
```

### Upgrade

```bash
helm upgrade geosnappro ./charts/geosnappro -n geosnappro
```

### Uninstall

```bash
helm uninstall geosnappro -n geosnappro
```

## 📝 Configuration

### Minimum Required Values

Only WireGuard credentials are required:

```yaml
gluetunApi:
  wireguard:
    privateKey: "your-private-key"
    addresses: "your-addresses"
```

### Common Customizations

```yaml
# Scale replicas
screenshotApi:
  replicaCount: 2

frontend:
  replicaCount: 2

# Change log level
screenshotApi:
  env:
    LOG_LEVEL: "INFO"

gluetunApi:
  config:
    logLevel: "INFO"

# Increase instance limit
gluetunApi:
  config:
    instanceLimit: 10

# Configure storage
frontend:
  mediaVolume:
    enabled: true
    size: 10Gi
    storageClass: "fast-ssd"
```

## 🔍 Troubleshooting

### Pods Not Starting?

```bash
# Check pod status
kubectl describe pod <pod-name> -n geosnappro

# Check events
kubectl get events -n geosnappro --sort-by='.lastTimestamp'
```

### Can't Access Service?

```bash
# Check service endpoints
kubectl get endpoints -n geosnappro

# Test from another pod
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n geosnappro -- \
  curl http://geosnappro-screenshot-api:8000/health
```

### Storage Issues?

```bash
# Check PVC
kubectl get pvc -n geosnappro

# Check storage class
kubectl get storageclass
```

## 📚 More Information

- **Detailed Guide**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Configuration Reference**: See [README.md](README.md)
- **Default Values**: See [values.yaml](values.yaml)
- **Production Example**: See [values-production.yaml](values-production.yaml)

## 💡 Quick Tips

1. **Use your own WireGuard credentials** - The default credentials in `values.yaml` are examples
2. **Enable autoscaling** - Set `screenshotApi.autoscaling.enabled: true` for production
3. **Configure ingress** - Enable ingress for external access instead of port-forwarding
4. **Set resource limits** - Configure CPU/memory limits for production workloads
5. **Use separate namespaces** - Deploy dev/staging/prod in different namespaces

## 🎯 Next Steps

1. ✅ Deploy the chart (you're here!)
2. 📊 Check pod status and logs
3. 🌐 Access the frontend
4. ⚙️ Customize configuration for your needs
5. 🚀 Deploy to production with proper ingress and resources

---

**Ready to deploy? Copy the commands from Step 1-3 above!** 🚀

