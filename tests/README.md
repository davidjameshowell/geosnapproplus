# Gluetun API Integration Tests

This directory contains integration tests for the Gluetun API service running in Docker.

## Test Coverage

The test suite validates all API endpoints by making actual HTTP requests to the running service:

- **GET /servers** - Retrieves the list of available Mullvad VPN servers
- **POST /start** - Starts a new Gluetun VPN container instance
- **POST /stop** - Stops a running Gluetun container
- **POST /destroy** - Destroys a Gluetun container and removes it from tracking
- **GET /status** - Gets the status of all running containers

## Prerequisites

Before running the tests, ensure the gluetun-api service is running:

```bash
# Start the gluetun-api service via docker-compose
docker-compose up -d gluetun-api

# Verify it's running
docker ps | grep gluetun-api
```

The service should be accessible at `http://localhost:8001` (or the URL specified in `GLUETUN_API_URL` environment variable).

## Installation

Install the test dependencies:

```bash
pip install -r requirements.txt
```

## Running the Tests

### Run All Tests

```bash
pytest test_gluetun_api.py -v
```

### Run Specific Test Classes

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

### Custom API URL

If your service is running on a different URL:

```bash
GLUETUN_API_URL=http://localhost:8001 pytest test_gluetun_api.py -v
```

## Test Structure

These are **integration tests** that make real HTTP requests to the running Docker container. The tests:

- Make actual HTTP requests to the API endpoints
- Create and destroy real Docker containers during testing
- Automatically clean up containers after each test
- Skip tests if the service is unavailable
- Handle real-world scenarios like instance limits and errors

### Test Classes

- `TestGetServers` - Tests for the `/servers` endpoint
- `TestStartGluetun` - Tests for the `/start` endpoint
- `TestStopGluetun` - Tests for the `/stop` endpoint
- `TestDestroyGluetun` - Tests for the `/destroy` endpoint
- `TestGetStatus` - Tests for the `/status` endpoint
- `TestIntegrationScenarios` - Integration tests for complete workflows

## Notes

- **Tests require Docker**: These tests interact with real Docker containers and require the Docker daemon to be running
- **Automatic Cleanup**: Tests automatically clean up containers they create
- **Service Availability**: Tests skip automatically if the API service is not available
- **Real API Calls**: All tests make actual HTTP requests to the running service
- **Container Lifecycle**: Tests validate complete container lifecycle (start -> status -> stop -> destroy)
- **Instance Limits**: Tests handle scenarios where instance limits are reached
- **Error Handling**: Tests validate proper error responses for invalid inputs

## Troubleshooting

If tests fail with connection errors:

1. Verify the service is running: `docker-compose ps gluetun-api`
2. Check service logs: `docker-compose logs gluetun-api`
3. Verify port mapping: `docker-compose port gluetun-api 8001`
4. Test manual connection: `curl http://localhost:8001/servers`

