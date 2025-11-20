# Gluetun Kubernetes Deployment Guide

This guide provides step-by-step instructions for deploying the Gluetun Kubernetes API to different Kubernetes environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [kind (Kubernetes in Docker)](#kind-kubernetes-in-docker)
3. [Minikube](#minikube)
4. [Production Kubernetes Cluster](#production-kubernetes-cluster)
5. [Verification](#verification)
6. [Common Issues](#common-issues)

---

## Prerequisites

### Required Tools

- **kubectl** (v1.24+): Kubernetes command-line tool
  ```bash
  kubectl version --client
  ```

- **Docker** (v20.10+): For building images
  ```bash
  docker --version
  ```

- **Git**: For cloning the repository
  ```bash
  git --version
  ```

### WireGuard Credentials

You need valid Mullvad WireGuard credentials:

1. **Private Key**: Your WireGuard private key
2. **Addresses**: Your WireGuard IP addresses (e.g., `10.67.123.45/32`)

To get these:
1. Log in to your Mullvad account
2. Go to "WireGuard configuration"
3. Generate a key or use an existing one
4. Note the private key and IP address

---

## kind (Kubernetes in Docker)

kind is ideal for local development and testing.

### Step 1: Install kind

```bash
# On Linux
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# On macOS
brew install kind

# Verify installation
kind version
```

### Step 2: Create kind Cluster

```bash
cd gluetun-k8s
./scripts/setup-kind-cluster.sh
```

This creates a cluster named `gluetun-test` with NodePort 30801 exposed to localhost.

**Manual creation (if script fails):**

```bash
cat <<EOF | kind create cluster --name gluetun-test --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30801
        hostPort: 30801
        protocol: TCP
EOF
```

### Step 3: Build and Load Image

```bash
./scripts/build-and-load.sh
```

This builds the Docker image and loads it directly into the kind cluster.

**Manual steps:**

```bash
docker build -t gluetun-k8s-api:latest .
kind load docker-image gluetun-k8s-api:latest --name gluetun-test
```

### Step 4: Deploy to Cluster

```bash
export WIREGUARD_PRIVATE_KEY="your-private-key-here"
export WIREGUARD_ADDRESSES="10.x.x.x/32"

./scripts/deploy.sh
```

### Step 5: Verify Deployment

```bash
# Check pod status
kubectl get pods -n gluetun-system

# Check logs
kubectl logs -n gluetun-system -l app=gluetun-k8s-api -f

# Test API
curl http://localhost:30801/health
```

### Step 6: Run Tests

```bash
export GLUETUN_K8S_API_URL=http://localhost:30801
./scripts/test.sh
```

---

## Minikube

Minikube is another great option for local Kubernetes testing.

### Step 1: Install Minikube

```bash
# On Linux
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# On macOS
brew install minikube

# Verify
minikube version
```

### Step 2: Start Minikube Cluster

```bash
minikube start --cpus=4 --memory=8192
```

### Step 3: Build Image in Minikube

```bash
# Use Minikube's Docker daemon
eval $(minikube docker-env)

# Build image
docker build -t gluetun-k8s-api:latest .
```

### Step 4: Deploy to Cluster

```bash
export WIREGUARD_PRIVATE_KEY="your-private-key-here"
export WIREGUARD_ADDRESSES="10.x.x.x/32"

./scripts/deploy.sh
```

### Step 5: Access the API

Since Minikube doesn't expose NodePorts directly, use one of these methods:

**Option A: Port Forwarding**

```bash
kubectl port-forward -n gluetun-system svc/gluetun-k8s-api 8001:8001
```

Then access at `http://localhost:8001`

**Option B: Minikube Service**

```bash
minikube service gluetun-k8s-api-nodeport -n gluetun-system
```

This opens the service in your browser and prints the URL.

**Option C: Get Minikube IP**

```bash
MINIKUBE_IP=$(minikube ip)
curl http://$MINIKUBE_IP:30801/health
```

### Step 6: Run Tests

```bash
# If using port-forward
export GLUETUN_K8S_API_URL=http://localhost:8001

# If using minikube IP
export GLUETUN_K8S_API_URL=http://$(minikube ip):30801

./scripts/test.sh
```

---

## Production Kubernetes Cluster

For production deployment on AWS EKS, GKE, AKS, or self-managed clusters.

### Step 1: Build and Push Image

```bash
# Build with version tag
docker build -t your-registry/gluetun-k8s-api:v1.0.0 .

# Push to registry
docker push your-registry/gluetun-k8s-api:v1.0.0

# For AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
docker tag gluetun-k8s-api:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/gluetun-k8s-api:v1.0.0
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/gluetun-k8s-api:v1.0.0
```

### Step 2: Update Deployment Manifest

Edit `k8s/04-deployment.yaml`:

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          image: your-registry/gluetun-k8s-api:v1.0.0
          imagePullPolicy: Always  # Change from IfNotPresent
```

### Step 3: Configure Namespace (Optional)

For production, you might want a dedicated namespace:

```yaml
# k8s/00-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: vpn-services  # Change from gluetun-system
```

Update `K8S_NAMESPACE` in all manifests accordingly.

### Step 4: Create Secret

```bash
kubectl create namespace gluetun-system

kubectl create secret generic gluetun-wireguard-credentials \
  --from-literal=wireguard-private-key="$WIREGUARD_PRIVATE_KEY" \
  --from-literal=wireguard-addresses="$WIREGUARD_ADDRESSES" \
  -n gluetun-system
```

### Step 5: Apply Manifests

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/02-rbac.yaml
kubectl apply -f k8s/03-configmap.yaml
kubectl apply -f k8s/04-deployment.yaml
kubectl apply -f k8s/05-service.yaml
```

### Step 6: Configure Access

**Option A: LoadBalancer Service**

Create `k8s/07-loadbalancer-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: gluetun-k8s-api-lb
  namespace: gluetun-system
spec:
  type: LoadBalancer
  ports:
    - name: http
      port: 80
      targetPort: 8001
  selector:
    app: gluetun-k8s-api
```

Apply and get external IP:

```bash
kubectl apply -f k8s/07-loadbalancer-service.yaml
kubectl get svc -n gluetun-system gluetun-k8s-api-lb
```

**Option B: Ingress**

Create `k8s/08-ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gluetun-k8s-api
  namespace: gluetun-system
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - gluetun-api.yourdomain.com
      secretName: gluetun-api-tls
  rules:
    - host: gluetun-api.yourdomain.com
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

Apply:

```bash
kubectl apply -f k8s/08-ingress.yaml
```

### Step 7: Configure Resource Limits

Update `k8s/04-deployment.yaml` for production workloads:

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "200m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

### Step 8: Enable Horizontal Pod Autoscaling (Optional)

Create `k8s/09-hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gluetun-k8s-api-hpa
  namespace: gluetun-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gluetun-k8s-api
  minReplicas: 2
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### Step 9: Monitoring and Logging

**Prometheus Monitoring:**

Add annotations to the deployment:

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8001"
    prometheus.io/path: "/metrics"
```

**Centralized Logging:**

Logs are automatically collected by cluster logging solutions (EFK, Loki, CloudWatch, etc.)

View logs:

```bash
kubectl logs -n gluetun-system -l app=gluetun-k8s-api --tail=100 -f
```

---

## Verification

### 1. Check Pod Status

```bash
kubectl get pods -n gluetun-system
```

Expected output:
```
NAME                              READY   STATUS    RESTARTS   AGE
gluetun-k8s-api-xxxxxxxxxx-xxxxx  1/1     Running   0          2m
```

### 2. Check Service

```bash
kubectl get svc -n gluetun-system
```

### 3. Check Logs

```bash
kubectl logs -n gluetun-system -l app=gluetun-k8s-api --tail=50
```

Look for:
```
INFO - Loaded in-cluster Kubernetes configuration
INFO - Fetched 150 Mullvad servers.
INFO - Running on http://0.0.0.0:8001
```

### 4. Test API Endpoints

```bash
# Health check
curl http://API_URL/health

# List servers
curl http://API_URL/servers | jq '.| length'

# Check status
curl http://API_URL/status
```

### 5. Create Test VPN Pod

```bash
curl -X POST http://API_URL/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA"}' | jq
```

Expected response:
```json
{
  "id": "uuid-here",
  "proxy": "http://username:password@10.x.x.x:8888",
  "pod_name": "gluetun-uuid-here",
  "pod_ip": "10.x.x.x"
}
```

### 6. Verify VPN Pod Created

```bash
kubectl get pods -n gluetun-system -l managed-by=gluetun-k8s-api
```

### 7. Test Proxy (from within cluster)

```bash
# Create test pod
kubectl run -it --rm test-curl --image=curlimages/curl -n gluetun-system -- sh

# Inside the pod, test proxy
curl -x http://username:password@POD_IP:8888 http://ifconfig.me
```

---

## Common Issues

### Issue: Pods Stuck in Pending

**Symptoms:**
```
NAME                              READY   STATUS    RESTARTS   AGE
gluetun-k8s-api-xxxxxxxxxx-xxxxx  0/1     Pending   0          5m
```

**Diagnosis:**
```bash
kubectl describe pod -n gluetun-system -l app=gluetun-k8s-api
```

**Common Causes:**
1. Insufficient cluster resources
2. Image pull errors
3. PVC binding issues

**Solutions:**
- Check resource availability: `kubectl top nodes`
- Verify image exists: `docker images | grep gluetun-k8s-api`
- Check events: `kubectl get events -n gluetun-system`

### Issue: ImagePullBackOff

**Symptoms:**
```
NAME                              READY   STATUS             RESTARTS   AGE
gluetun-k8s-api-xxxxxxxxxx-xxxxx  0/1     ImagePullBackOff   0          3m
```

**Solutions:**

For kind:
```bash
# Reload image
kind load docker-image gluetun-k8s-api:latest --name gluetun-test
kubectl rollout restart deployment -n gluetun-system gluetun-k8s-api
```

For production:
```bash
# Verify image exists in registry
docker pull your-registry/gluetun-k8s-api:v1.0.0

# Check imagePullSecrets if using private registry
kubectl create secret docker-registry regcred \
  --docker-server=your-registry \
  --docker-username=username \
  --docker-password=password \
  -n gluetun-system
```

### Issue: API Not Accessible

**Symptoms:**
```bash
curl: (7) Failed to connect to localhost port 30801
```

**Solutions:**

For kind:
```bash
# Verify port mapping
docker ps | grep gluetun-test

# Recreate cluster with port mapping
kind delete cluster --name gluetun-test
./scripts/setup-kind-cluster.sh
```

For minikube:
```bash
# Use port-forward
kubectl port-forward -n gluetun-system svc/gluetun-k8s-api 8001:8001

# Or use minikube service
minikube service gluetun-k8s-api-nodeport -n gluetun-system
```

### Issue: Permission Denied Errors

**Symptoms:**
```
Error creating pod: pods is forbidden: User "system:serviceaccount:gluetun-system:gluetun-k8s-api" cannot create resource "pods"
```

**Solutions:**
```bash
# Verify RBAC is applied
kubectl get role -n gluetun-system gluetun-k8s-api
kubectl get rolebinding -n gluetun-system gluetun-k8s-api

# Reapply RBAC
kubectl apply -f k8s/02-rbac.yaml

# Restart deployment
kubectl rollout restart deployment -n gluetun-system gluetun-k8s-api
```

### Issue: Gluetun Pods Failing

**Symptoms:**
Gluetun VPN pods created via /start endpoint fail to start or crash.

**Diagnosis:**
```bash
kubectl get pods -n gluetun-system -l managed-by=gluetun-k8s-api
kubectl logs -n gluetun-system POD_NAME
```

**Common Causes:**
1. Invalid WireGuard credentials
2. Missing NET_ADMIN capability
3. Network policy restrictions

**Solutions:**
```bash
# Verify credentials
kubectl get secret gluetun-wireguard-credentials -n gluetun-system -o yaml

# Check pod security context
kubectl get pod POD_NAME -n gluetun-system -o jsonpath='{.spec.containers[0].securityContext}'

# Test with debug pod
kubectl run -it --rm debug-gluetun --image=qmcgaw/gluetun \
  --namespace=gluetun-system \
  --overrides='{"spec":{"containers":[{"name":"gluetun","image":"qmcgaw/gluetun","securityContext":{"capabilities":{"add":["NET_ADMIN"]}}}]}}' \
  -- sh
```

---

## Cleanup

### Remove Deployment

```bash
./scripts/undeploy.sh
```

Or manually:

```bash
kubectl delete -f k8s/
```

### Delete Namespace

```bash
kubectl delete namespace gluetun-system
```

### Delete kind Cluster

```bash
kind delete cluster --name gluetun-test
```

### Stop Minikube

```bash
minikube stop
minikube delete
```

---

## Next Steps

- Review the [README](README.md) for API documentation
- Run the test suite: `./scripts/test.sh`
- Integrate with your application
- Set up monitoring and alerting
- Configure backup and disaster recovery

For additional help, check the troubleshooting section in the main README.

