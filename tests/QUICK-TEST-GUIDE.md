# Quick Test Guide - Unified Chart E2E Tests

## 🚀 Run Tests in 3 Steps

### Step 1: Create Kubernetes Cluster

```bash
# Using Kind (recommended)
kind create cluster --name geosnappro-test

# OR using Minikube
minikube start
```

### Step 2: Install Dependencies

```bash
pip install pytest requests
```

### Step 3: Run Tests

```bash
cd /home/david/repos/geosnappro-thefinal
pytest tests/test_kind_e2e.py -v -s
```

## 🌐 Validate Frontend Manually

When tests run, you'll see:

```
================================================================================
✅ Port Forwarding Active!
================================================================================
Access Services:
  • Frontend:       http://127.0.0.1:5000  ← Open this in your browser!
  • Screenshot API: http://127.0.0.1:28080
  • Gluetun API:    http://127.0.0.1:28081
================================================================================
```

**Open http://127.0.0.1:5000 in your browser while tests are running!**

## 🔍 What Gets Deployed

The tests deploy the **unified Helm chart** at `charts/geosnappro/` which includes:

- ✅ Screenshot API (port 8000)
- ✅ Gluetun API (port 8001)
- ✅ Frontend (port 5000)

All from **one single chart**, not separate charts!

## 🛑 Keep Environment Running

To keep the deployment active for manual testing:

```bash
# Skip cleanup after tests
E2E_SKIP_CLEANUP=true pytest tests/test_kind_e2e.py -v -s

# Then access frontend at http://127.0.0.1:5000
```

Manual cleanup when done:
```bash
helm uninstall geosnappro-e2e -n geosnap-e2e
```

## 📝 Run Specific Tests

```bash
# Test unified chart deployment
pytest tests/test_kind_e2e.py::test_unified_chart_all_services_deployed -v -s

# Test frontend only
pytest tests/test_kind_e2e.py::test_frontend_homepage -v -s

# Test all health endpoints
pytest tests/test_kind_e2e.py::test_gluetun_health -v -s
pytest tests/test_kind_e2e.py::test_screenshot_api_health -v -s
```

## 🐛 Quick Troubleshooting

### Pods Not Ready?
```bash
kubectl get pods -n geosnap-e2e
kubectl logs -n geosnap-e2e -l app.kubernetes.io/instance=geosnappro-e2e
```

### Port Already in Use?
```bash
# Find what's using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>
```

### Need More Time?
```bash
# Increase timeout
E2E_HELM_INSTALL_TIMEOUT=600 pytest tests/test_kind_e2e.py -v -s
```

## 📚 Full Documentation

See [README-E2E.md](README-E2E.md) for complete documentation.

---

**TL;DR**: Run `pytest tests/test_kind_e2e.py -v -s` and open http://127.0.0.1:5000 to validate the frontend! 🎉

