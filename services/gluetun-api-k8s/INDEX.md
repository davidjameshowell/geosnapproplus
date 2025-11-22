# Gluetun Kubernetes API - Documentation Index

## 🎯 Start Here

New to this project? Follow this path:

1. **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** - 5-minute project overview
2. **[QUICK_START.md](QUICK_START.md)** - Get started in 5 minutes
3. **[README.md](README.md)** - Complete documentation and API reference

## 📖 Documentation Files

### Getting Started
- **[QUICK_START.md](QUICK_START.md)** - Fastest way to get up and running
  - Prerequisites
  - 5-minute setup
  - Basic usage
  - Common commands

### Complete Guide
- **[README.md](README.md)** - Main documentation (600+ lines)
  - Overview and architecture
  - Prerequisites and installation
  - Complete API reference
  - Configuration options
  - Development guide
  - Troubleshooting

### Deployment
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Detailed deployment (500+ lines)
  - kind cluster setup
  - Minikube deployment
  - Production Kubernetes deployment
  - Verification steps
  - Common issues and solutions

### Technical Details
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Technical overview (400+ lines)
  - Implementation details
  - Architecture decisions
  - Performance characteristics
  - Security considerations
  - Comparison with Docker implementation

### Project Information
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** - High-level overview
  - Project summary
  - What's included
  - Statistics
  - Key features
  - Implementation status

### Examples
- **[examples/README.md](examples/README.md)** - Usage examples
  - Python example
  - Shell scripts
  - curl commands
  - Multi-language examples (JavaScript, Go)
  - Advanced usage patterns

## 🚀 Quick Navigation

### I want to...

#### ...get started quickly
→ [QUICK_START.md](QUICK_START.md)

#### ...deploy to kind
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#kind-kubernetes-in-docker)

#### ...deploy to production
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#production-kubernetes-cluster)

#### ...understand the API
→ [README.md](README.md#api-endpoints)

#### ...see code examples
→ [examples/README.md](examples/README.md)

#### ...understand the implementation
→ [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

#### ...troubleshoot issues
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#common-issues)

#### ...configure the system
→ [README.md](README.md#configuration)

## 📂 Code Files

### Application Code
- **[app.py](app.py)** - Flask REST API server
- **[k8s_manager.py](k8s_manager.py)** - Kubernetes API manager
- **[config.py](config.py)** - Configuration management

### Kubernetes Resources
- **[k8s/00-namespace.yaml](k8s/00-namespace.yaml)** - Namespace
- **[k8s/01-secret.yaml](k8s/01-secret.yaml)** - Secret template
- **[k8s/02-rbac.yaml](k8s/02-rbac.yaml)** - RBAC configuration
- **[k8s/03-configmap.yaml](k8s/03-configmap.yaml)** - ConfigMap
- **[k8s/04-deployment.yaml](k8s/04-deployment.yaml)** - Deployment
- **[k8s/05-service.yaml](k8s/05-service.yaml)** - ClusterIP Service
- **[k8s/06-nodeport-service.yaml](k8s/06-nodeport-service.yaml)** - NodePort Service

### Scripts
- **[scripts/setup-kind-cluster.sh](scripts/setup-kind-cluster.sh)** - Create kind cluster
- **[scripts/build-and-load.sh](scripts/build-and-load.sh)** - Build and load image
- **[scripts/deploy.sh](scripts/deploy.sh)** - Deploy to cluster
- **[scripts/undeploy.sh](scripts/undeploy.sh)** - Remove deployment
- **[scripts/test.sh](scripts/test.sh)** - Run tests

### Tests
- **[tests/test_gluetun_k8s_api.py](tests/test_gluetun_k8s_api.py)** - Test suite

### Examples
- **[examples/api_usage.py](examples/api_usage.py)** - Python usage example

## 🎓 Learning Path

### Beginner
1. Read [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
2. Follow [QUICK_START.md](QUICK_START.md)
3. Explore [examples/README.md](examples/README.md)

### Developer
1. Review [README.md](README.md) API reference
2. Study [app.py](app.py) and [k8s_manager.py](k8s_manager.py)
3. Examine [tests/test_gluetun_k8s_api.py](tests/test_gluetun_k8s_api.py)
4. Read [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

### DevOps Engineer
1. Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
2. Review [k8s/](k8s/) manifests
3. Understand [scripts/](scripts/) automation
4. Study [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) security section

## 📊 Project Statistics

- **Total Files**: 27
- **Lines of Code & Documentation**: 4,342+
- **Documentation Files**: 6
- **Python Files**: 4
- **Kubernetes Manifests**: 7
- **Shell Scripts**: 5
- **Test Files**: 1

## 🔍 Find Specific Information

### API Reference
- Endpoints: [README.md#api-endpoints](README.md#api-endpoints)
- Examples: [examples/README.md](examples/README.md)

### Configuration
- Environment Variables: [README.md#configuration](README.md#configuration)
- Kubernetes Config: [k8s/03-configmap.yaml](k8s/03-configmap.yaml)

### Deployment
- kind: [DEPLOYMENT_GUIDE.md#kind-kubernetes-in-docker](DEPLOYMENT_GUIDE.md#kind-kubernetes-in-docker)
- Minikube: [DEPLOYMENT_GUIDE.md#minikube](DEPLOYMENT_GUIDE.md#minikube)
- Production: [DEPLOYMENT_GUIDE.md#production-kubernetes-cluster](DEPLOYMENT_GUIDE.md#production-kubernetes-cluster)

### Troubleshooting
- Common Issues: [DEPLOYMENT_GUIDE.md#common-issues](DEPLOYMENT_GUIDE.md#common-issues)
- Debugging: [README.md#troubleshooting](README.md#troubleshooting)

### Architecture
- Overview: [README.md#architecture](README.md#architecture)
- Technical Details: [IMPLEMENTATION_SUMMARY.md#architecture](IMPLEMENTATION_SUMMARY.md#architecture)

### Security
- RBAC: [k8s/02-rbac.yaml](k8s/02-rbac.yaml)
- Secrets: [k8s/01-secret.yaml](k8s/01-secret.yaml)
- Considerations: [IMPLEMENTATION_SUMMARY.md#security-considerations](IMPLEMENTATION_SUMMARY.md#security-considerations)

## 📞 Quick Commands

### Setup
```bash
./scripts/setup-kind-cluster.sh
./scripts/build-and-load.sh
export WIREGUARD_PRIVATE_KEY="..."
export WIREGUARD_ADDRESSES="..."
./scripts/deploy.sh
```

### Test
```bash
./scripts/test.sh
```

### Use
```bash
curl http://localhost:30801/health
curl http://localhost:30801/servers | jq
```

### Cleanup
```bash
./scripts/undeploy.sh
kind delete cluster --name gluetun-test
```

## 🎯 Common Tasks

| Task | Documentation | File |
|------|---------------|------|
| Start a VPN pod | [README.md](README.md#start-vpn-pod) | [app.py](app.py) |
| List servers | [README.md](README.md#list-servers) | [app.py](app.py) |
| Deploy to kind | [QUICK_START.md](QUICK_START.md) | [scripts/deploy.sh](scripts/deploy.sh) |
| Run tests | [QUICK_START.md](QUICK_START.md#9-run-automated-tests) | [scripts/test.sh](scripts/test.sh) |
| Troubleshoot | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#common-issues) | - |
| Configure | [README.md](README.md#configuration) | [config.py](config.py) |

## 🌟 Highlights

- ✅ Complete REST API implementation
- ✅ Kubernetes-native architecture
- ✅ Comprehensive test suite
- ✅ Production-ready manifests
- ✅ Automated deployment scripts
- ✅ 4,300+ lines of code and documentation
- ✅ Multi-environment support
- ✅ Security best practices

## 📅 Document Status

All documentation is current and complete as of 2025-11-09.

## 🚀 Ready to Begin?

Start with: **[QUICK_START.md](QUICK_START.md)** → 5-minute setup guide

---

*This index helps you navigate the Gluetun Kubernetes API documentation.*

