# GeoSnappro Integration Tests

This directory contains integration tests for the GeoSnappro services running in Docker and Kubernetes.

## Test Structure

Each service has its own testing workflow:

- **Kind End-to-End Stack Tests** - `run_kind_e2e.sh`
- **Frontend Tests** - Located in `../frontend/tests/`
- **Gluetun API Tests** - Located in `./test_gluetun_api.py`

## Kind End-to-End Tests

Use the Kind E2E workflow to validate the full stack (frontend, screenshot API, and Gluetun API) inside an ephemeral Kubernetes cluster.

### Prerequisites

- Docker daemon running locally
- [`kind`](https://kind.sigs.k8s.io/docs/user/quick-start/)
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/)
- [`helm`](https://helm.sh/docs/intro/install/)
- Python 3 (for pytest)

### Quick Start

```bash
./tests/run_kind_e2e.sh
```

The script performs the following:

- Creates (or reuses) a Kind cluster
- Builds local Docker images for the frontend, screenshot API, and Gluetun API
- Loads the images into the cluster and deploys the Helm charts
- Seeds Gluetun with a mock Mullvad server list and dummy WireGuard credentials suitable for smoke tests
- Leaves the cluster running for manual validation (tests are skipped by default)

The cluster remains up after the script finishes so you can port-forward and explore services. When finished, delete it manually:

```bash
kind delete cluster --name geosnap-e2e
```

Available environment overrides include:

- `SKIP_TESTS=false` – also run the pytest smoke suite
- `SKIP_BUILD=true` – reuse already-built images
- `KEEP_CLUSTER=false` – automatically remove the Kind cluster on exit
- `IMAGE_TAG=custom-tag` – change the tag applied to locally built images
- `NAMESPACE=custom-ns` – change the deployment namespace
- `PYTEST_ARGS="--maxfail=1 -vv"` – pass extra flags to pytest

## Frontend Tests

The frontend service tests are located in the `frontend/tests/` directory. For detailed information about running the frontend tests, please refer to:

```
../frontend/tests/README.md
```

## Gluetun API Tests

This directory contains integration tests for the Gluetun API service running in Docker.

### Test Coverage

The test suite validates all API endpoints by making actual HTTP requests to the running service:

- **GET /servers** - Retrieves the list of available Mullvad VPN servers
- **POST /start** - Starts a new Gluetun VPN container instance
- **POST /stop** - Stops a running Gluetun container
- **POST /destroy** - Destroys a Gluetun container and removes it from tracking
- **GET /status** - Gets the status of all running containers

### Prerequisites

Before running the tests, ensure the gluetun-api service is running:

```bash
# Start the gluetun-api service via docker-compose
docker-compose up -d gluetun-api

# Verify it's running
docker ps | grep gluetun-api
```

The service should be accessible at `http://localhost:8001` (or the URL specified in `GLUETUN_API_URL` environment variable).

### Installation

Install the test dependencies:

```bash
pip install -r requirements.txt
```

### Running the Tests

#### Run All Tests

```bash
pytest test_gluetun_api.py -v
```

#### Run Specific Test Classes

```bash
# Test server retrieval
pytest test_gluetun_api.py::TestGetServers -v

# Test container starting
pytest test_gluetun_api.py::TestStartGluetun -v

# Test container stopping
pytest test_gluetun_api.py::TestStopGluetun -v

# Test container destruction
pytest test_gluetun_api.py::TestDestroyGluetun -v

# Test status endpoint
pytest test_gluetun_api.py::TestGetStatus -v

# Test integration scenarios
pytest test_gluetun_api.py::TestIntegrationScenarios -v
```

#### Custom API URL

If your service is running on a different URL:

```bash
GLUETUN_API_URL=http://localhost:8001 pytest test_gluetun_api.py -v
```

### Test Structure

These are **integration tests** that make real HTTP requests to the running Docker container. The tests:

- Make actual HTTP requests to the API endpoints
- Create and destroy real Docker containers during testing
- Automatically clean up containers after each test
- Skip tests if the service is unavailable
- Handle real-world scenarios like instance limits and errors

#### Test Classes

- `TestGetServers` - Tests for the `/servers` endpoint
- `TestStartGluetun` - Tests for the `/start` endpoint
- `TestStopGluetun` - Tests for the `/stop` endpoint
- `TestDestroyGluetun` - Tests for the `/destroy` endpoint
- `TestGetStatus` - Tests for the `/status` endpoint
- `TestIntegrationScenarios` - Integration tests for complete workflows

### Notes

- **Tests require Docker**: These tests interact with real Docker containers and require the Docker daemon to be running
- **Automatic Cleanup**: Tests automatically clean up containers they create
- **Service Availability**: Tests skip automatically if the API service is not available
- **Real API Calls**: All tests make actual HTTP requests to the running service
- **Container Lifecycle**: Tests validate complete container lifecycle (start -> status -> stop -> destroy)
- **Instance Limits**: Tests handle scenarios where instance limits are reached
- **Error Handling**: Tests validate proper error responses for invalid inputs

### Troubleshooting

If tests fail with connection errors:

1. Verify the service is running: `docker-compose ps gluetun-api`
2. Check service logs: `docker-compose logs gluetun-api`
3. Verify port mapping: `docker-compose port gluetun-api 8001`
4. Test manual connection: `curl http://localhost:8001/servers`

