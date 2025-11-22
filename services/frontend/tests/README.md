# Frontend Service Tests

This directory contains integration tests for the GeoSnappro frontend service.

## Test Coverage

The test suite validates the frontend service by making actual HTTP requests to the running service:

- **Basic Connectivity** - Tests that the frontend service responds to HTTP requests
- **Content Validation** - Tests that the frontend returns meaningful content
- **Static Assets** - Tests that static assets are accessible
- **Backend Connectivity** - Tests connectivity between frontend and backend services
- **Kubernetes Environment** - Tests that the frontend is properly configured in Kubernetes
- **Integration Scenarios** - Tests complete workflows through the application

## Prerequisites

Before running the tests, ensure the following services are running:

1. **Frontend Service** - The GeoSnappro frontend application
2. **Backend Service** - The screenshot API service
3. **Gluetun API Service** - The Gluetun API service

## Running Tests

### Running Tests Locally

If you're running the services locally with docker-compose:

```bash
# Start all services
docker-compose up -d

# Run the tests
FRONTEND_URL=http://localhost:5000 BACKEND_URL=http://localhost:8000 GLUETUN_API_URL=http://localhost:8001 python -m pytest test_frontend.py -v
```

### Running Tests in Kubernetes

#### Option 1: Using the Test Script

The easiest way to run tests in Kubernetes is to use the provided test script:

```bash
# Make the script executable (if not already done)
chmod +x run_k8s_tests.sh

# Run the tests
./run_k8s_tests.sh
```

This script will:
1. Deploy the frontend using the Helm chart
2. Determine the appropriate URLs for the services
3. Run the tests against the deployed services
4. Clean up the deployment (optional)

#### Option 2: Manual Kubernetes Deployment

If you prefer to deploy the services manually:

1. Deploy the frontend using the Helm chart:
   ```bash
   helm install frontend ../../charts/frontend
   ```

2. Build and deploy the test container:
   ```bash
   # Build the test image
   docker build -t frontend-test:latest -f Dockerfile .
   
   # Apply the test job
   kubectl apply -f test-job.yaml
   ```

3. Check the test results:
   ```bash
   # Get the pod name
   POD_NAME=$(kubectl get pods -l app=frontend-test -o jsonpath='{.items[0].metadata.name}')
   
   # View the logs
   kubectl logs $POD_NAME
   ```

## Test Classes

### TestFrontendConnectivity

Tests basic connectivity to the frontend service:
- `test_frontend_responds` - Verifies the frontend responds to HTTP requests
- `test_frontend_has_content` - Verifies the frontend returns meaningful content
- `test_frontend_static_assets` - Verifies static assets are accessible

### TestFrontendBackendConnectivity

Tests connectivity between frontend and backend services:
- `test_backend_servers_endpoint` - Verifies the backend servers endpoint is accessible
- `test_backend_status_endpoint` - Verifies the backend status endpoint is accessible
- `test_frontend_uses_backend_config` - Verifies the frontend is configured with the correct backend URL

### TestFrontendInKubernetes

Tests frontend when running in Kubernetes:
- `test_frontend_pod_environment` - Verifies the frontend pod has the correct environment variables
- `test_frontend_service_discovery` - Verifies the frontend can discover other services via DNS
- `test_frontend_media_volume` - Verifies the frontend media volume is accessible

### TestFrontendIntegration

Integration tests for the frontend service:
- `test_complete_workflow` - Tests a complete workflow from frontend to backend to gluetun
- `test_error_handling` - Tests that the frontend handles errors gracefully
- `test_concurrent_requests` - Tests that the frontend can handle concurrent requests

## Configuration

The tests can be configured using the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `FRONTEND_URL` | URL of the frontend service | `http://localhost:5000` |
| `BACKEND_URL` | URL of the backend service | `http://localhost:8000` |
| `GLUETUN_API_URL` | URL of the Gluetun API service | `http://localhost:8001` |

## Running Specific Tests

You can run specific test classes or methods:

```bash
# Run a specific test class
python -m pytest test_frontend.py::TestFrontendConnectivity -v

# Run a specific test method
python -m pytest test_frontend.py::TestFrontendConnectivity::test_frontend_responds -v

# Run tests matching a pattern
python -m pytest test_frontend.py -k "connectivity" -v
```

## Troubleshooting

If tests fail with connection errors:

1. **Verify Services are Running**:
   ```bash
   # For docker-compose
   docker-compose ps
   
   # For Kubernetes
   kubectl get pods
   kubectl get services
   ```

2. **Check Service Logs**:
   ```bash
   # For docker-compose
   docker-compose logs frontend
   
   # For Kubernetes
   kubectl logs -l app=frontend
   ```

3. **Verify Port Mapping**:
   ```bash
   # For docker-compose
   docker-compose port frontend 5000
   
   # For Kubernetes
   kubectl get service frontend
   ```

4. **Test Manual Connection**:
   ```bash
   curl http://localhost:5000
   ```

## Notes

- **Tests are Integration Tests**: These tests make real HTTP requests to the running services.
- **Service Availability**: Tests skip automatically if the required services are not available.
- **Kubernetes Detection**: Some tests only run when in a Kubernetes environment.
- **Concurrent Testing**: Tests include concurrent request handling to validate performance under load.
