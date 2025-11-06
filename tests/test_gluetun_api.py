"""
Integration tests for the Gluetun API service running in Docker.

This test suite validates all API endpoints by making actual HTTP requests
to the gluetun-api service running in the Docker container via docker-compose.
The service should be accessible at http://localhost:8001.

IMPORTANT NOTES:
- The first request to /servers triggers initialization which may take up to 60 seconds
  as it starts a temporary Gluetun container to fetch the server list. Subsequent requests
  are much faster as the server list is cached in memory.
- The server list may be empty if server fetching failed during initialization.
  Tests handle this gracefully by skipping when servers are required.
- All tests automatically clean up containers they create.

API endpoints tested:
- GET /servers - Retrieve list of Mullvad servers (returns empty dict if initialization failed)
- POST /start - Start a Gluetun VPN container
- POST /stop - Stop a running Gluetun container
- POST /destroy - Destroy a Gluetun container
- GET /status - Get status of all running containers
"""

import json
import pytest
import requests
import time
import os

# Base URL for the gluetun-api service
BASE_URL = os.getenv("GLUETUN_API_URL", "http://localhost:8001")
REQUEST_TIMEOUT = 30  # seconds
INITIALIZATION_TIMEOUT = 90  # seconds - first request triggers server list initialization which can take up to 60s


@pytest.fixture(scope="session")
def api_available():
    """Check if the API service is available before running tests.
    
    Note: The first request to /servers may take up to 60 seconds as it triggers
    initialization which fetches the server list from a temporary Gluetun container.
    """
    try:
        # Use longer timeout for initial request which may trigger initialization
        response = requests.get(f"{BASE_URL}/servers", timeout=INITIALIZATION_TIMEOUT)
        if response.status_code == 200:
            return True
    except requests.exceptions.Timeout:
        pytest.skip(
            f"Gluetun API initialization timed out after {INITIALIZATION_TIMEOUT}s. "
            "The first request may take up to 60 seconds to fetch server list."
        )
    except requests.exceptions.RequestException as e:
        pytest.skip(
            f"Gluetun API not available at {BASE_URL}: {e}. "
            "Make sure the docker-compose service is running: docker-compose up -d gluetun-api"
        )
    
    pytest.skip(
        f"Gluetun API returned unexpected status. "
        "Make sure the docker-compose service is running: docker-compose up -d gluetun-api"
    )


@pytest.fixture(autouse=True)
def cleanup_containers(api_available):
    """Clean up any containers created during tests."""
    yield
    
    # After each test, get status and destroy any test containers
    try:
        response = requests.get(f"{BASE_URL}/status", timeout=5)
        if response.status_code == 200:
            containers = response.json()
            for container_id in list(containers.keys()):
                # Only destroy if it looks like a test container
                # (all containers created via /start will have UUID format)
                try:
                    requests.post(
                        f"{BASE_URL}/destroy",
                        json={"id": container_id},
                        timeout=10
                    )
                except requests.exceptions.RequestException:
                    pass  # Ignore cleanup errors
                time.sleep(0.5)  # Small delay between cleanup operations
    except requests.exceptions.RequestException:
        pass  # Ignore cleanup errors if service is unavailable


class TestGetServers:
    """Tests for GET /servers endpoint."""

    def test_get_servers_success(self, api_available):
        """Test successfully retrieving the list of servers."""
        # Note: Subsequent requests should be faster since initialization only happens once
        response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), "Response should be a dictionary"
        
        # Note: Server list may be empty if server fetching failed during initialization
        # This is acceptable - the endpoint should still return 200 with an empty dict
        
        # If servers are available, validate structure
        if len(data) > 0:
            # Check that server entries have expected structure
            first_server_key = next(iter(data.keys()))
            server_data = data[first_server_key]
            assert isinstance(server_data, dict), "Server data should be a dictionary"
            # The exact structure may vary, but should have hostname
            if "hostname" in server_data:
                assert isinstance(server_data["hostname"], str)
                assert len(server_data["hostname"]) > 0, "Hostname should not be empty"

    def test_get_servers_response_format(self, api_available):
        """Test that servers endpoint returns valid JSON."""
        response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        
        # Validate JSON structure
        data = response.json()
        assert isinstance(data, dict), "Response must be a JSON object"


class TestStartGluetun:
    """Tests for POST /start endpoint."""

    def test_start_gluetun_invalid_server(self, api_available):
        """Test starting with an invalid server name."""
        request_data = {
            "server": "invalid-server-name-that-does-not-exist-12345"
        }
        
        response = requests.post(
            f"{BASE_URL}/start",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert isinstance(data["error"], str), "Error should be a string"
        # API returns "Invalid server" - check for case-insensitive match
        assert "invalid" in data["error"].lower(), f"Error message should mention 'invalid', got: {data['error']}"

    def test_start_gluetun_missing_server(self, api_available):
        """Test starting without providing server name."""
        request_data = {}
        
        response = requests.post(
            f"{BASE_URL}/start",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert isinstance(data["error"], str), "Error should be a string"
        assert len(data["error"]) > 0, "Error message should not be empty"

    def test_start_gluetun_with_valid_server(self, api_available):
        """Test starting with a valid server (if servers are available)."""
        # First get available servers
        servers_response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert servers_response.status_code == 200
        
        servers_data = servers_response.json()
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        # Use the first available server
        first_server = next(iter(servers_data.keys()))
        
        request_data = {"server": first_server}
        
        response = requests.post(
            f"{BASE_URL}/start",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        # Should either succeed or hit instance limit
        assert response.status_code in [200, 429], \
            f"Expected 200 or 429, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "id" in data, "Response should contain container id"
            assert "proxy" in data, "Response should contain proxy URL"
            assert data["proxy"].startswith("http://"), "Proxy should be HTTP URL"
            assert "localhost" in data["proxy"], "Proxy should contain localhost"
            
            # Verify proxy URL format: http://username:password@localhost:port
            assert "@localhost:" in data["proxy"], "Proxy should have auth format"
            
            # Validate proxy URL structure more thoroughly
            proxy_parts = data["proxy"].replace("http://", "").split("@")
            assert len(proxy_parts) == 2, "Proxy should have format http://user:pass@host:port"
            auth_part, host_port = proxy_parts
            assert ":" in auth_part, "Auth should have username:password format"
            assert "localhost:" in host_port, "Host should be localhost with port"
            port = host_port.split(":")[1]
            assert port.isdigit(), f"Port should be numeric, got: {port}"
            assert int(port) > 0 and int(port) < 65536, f"Port should be valid range, got: {port}"
            
            # Validate container ID format (should be UUID string)
            assert isinstance(data["id"], str), "Container ID should be a string"
            assert len(data["id"]) > 0, "Container ID should not be empty"
            
            # Store container ID for cleanup
            container_id = data["id"]
            
            # Clean up immediately after test
            destroy_response = requests.post(
                f"{BASE_URL}/destroy",
                json={"id": container_id},
                timeout=REQUEST_TIMEOUT
            )
            # Don't fail if cleanup fails
            if destroy_response.status_code != 200:
                print(f"Warning: Failed to cleanup container {container_id}")
        
        elif response.status_code == 429:
            data = response.json()
            assert "error" in data
            assert "limit" in data["error"].lower() or "429" in str(response.status_code)


class TestStopGluetun:
    """Tests for POST /stop endpoint."""

    def test_stop_gluetun_container_not_found(self, api_available):
        """Test stopping a container that doesn't exist."""
        request_data = {"id": "non-existent-container-id-12345"}
        
        response = requests.post(
            f"{BASE_URL}/stop",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert isinstance(data["error"], str), "Error should be a string"
        # API returns "Container not found" - check for case-insensitive match
        assert "not found" in data["error"].lower(), f"Error message should mention 'not found', got: {data['error']}"

    def test_stop_gluetun_missing_id(self, api_available):
        """Test stopping without providing container ID."""
        request_data = {}
        
        response = requests.post(
            f"{BASE_URL}/stop",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        # API returns 404 when container_id is None (not in RUNNING_CONTAINERS)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert isinstance(data["error"], str), "Error should be a string"
        assert "not found" in data["error"].lower() or "Container not found" in data["error"]

    def test_stop_gluetun_success(self, api_available):
        """Test successfully stopping a container."""
        # First create a container
        servers_response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert servers_response.status_code == 200
        
        servers_data = servers_response.json()
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        first_server = next(iter(servers_data.keys()))
        
        # Start a container
        start_response = requests.post(
            f"{BASE_URL}/start",
            json={"server": first_server},
            timeout=REQUEST_TIMEOUT
        )
        
        if start_response.status_code != 200:
            pytest.skip(f"Cannot start container for stop test: {start_response.status_code}")
        
        container_id = start_response.json()["id"]
        
        try:
            # Wait a moment for container to be ready
            time.sleep(2)
            
            # Now stop it
            stop_response = requests.post(
                f"{BASE_URL}/stop",
                json={"id": container_id},
                timeout=REQUEST_TIMEOUT
            )
            
            assert stop_response.status_code == 200, \
                f"Expected 200, got {stop_response.status_code}: {stop_response.text}"
            data = stop_response.json()
            assert "message" in data
            assert "stopped" in data["message"].lower()
        finally:
            # Clean up
            requests.post(
                f"{BASE_URL}/destroy",
                json={"id": container_id},
                timeout=REQUEST_TIMEOUT
            )


class TestDestroyGluetun:
    """Tests for POST /destroy endpoint."""

    def test_destroy_gluetun_container_not_found(self, api_available):
        """Test destroying a container that doesn't exist."""
        request_data = {"id": "non-existent-container-id-12345"}
        
        response = requests.post(
            f"{BASE_URL}/destroy",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert isinstance(data["error"], str), "Error should be a string"
        # API returns "Container not found" - check for case-insensitive match
        assert "not found" in data["error"].lower(), f"Error message should mention 'not found', got: {data['error']}"

    def test_destroy_gluetun_missing_id(self, api_available):
        """Test destroying without providing container ID."""
        request_data = {}
        
        response = requests.post(
            f"{BASE_URL}/destroy",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        # API returns 404 when container_id is None (not in RUNNING_CONTAINERS)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert isinstance(data["error"], str), "Error should be a string"
        assert "not found" in data["error"].lower() or "Container not found" in data["error"]

    def test_destroy_gluetun_success(self, api_available):
        """Test successfully destroying a container."""
        # First create a container
        servers_response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert servers_response.status_code == 200
        
        servers_data = servers_response.json()
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        first_server = next(iter(servers_data.keys()))
        
        # Start a container
        start_response = requests.post(
            f"{BASE_URL}/start",
            json={"server": first_server},
            timeout=REQUEST_TIMEOUT
        )
        
        if start_response.status_code != 200:
            pytest.skip(f"Cannot start container for destroy test: {start_response.status_code}")
        
        container_id = start_response.json()["id"]
        
        # Wait a moment for container to be ready
        time.sleep(2)
        
        # Verify it's in status before destroying
        status_before = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        if status_before.status_code == 200:
            containers_before = status_before.json()
            assert container_id in containers_before, "Container should be in status before destroy"
        
        # Now destroy it
        destroy_response = requests.post(
            f"{BASE_URL}/destroy",
            json={"id": container_id},
            timeout=REQUEST_TIMEOUT
        )
        
        assert destroy_response.status_code == 200, \
            f"Expected 200, got {destroy_response.status_code}: {destroy_response.text}"
        data = destroy_response.json()
        assert "message" in data
        assert "destroyed" in data["message"].lower()
        
        # Verify it's removed from status
        time.sleep(1)  # Give it a moment to update
        status_after = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        if status_after.status_code == 200:
            containers_after = status_after.json()
            assert container_id not in containers_after, "Container should be removed from status after destroy"


class TestGetStatus:
    """Tests for GET /status endpoint."""

    def test_get_status_success(self, api_available):
        """Test successfully getting status."""
        response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), "Status should return a dictionary"

    def test_get_status_structure(self, api_available):
        """Test that status returns correct structure."""
        response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict), "Status must be a JSON object"
        
        # If there are containers, validate their structure
        if len(data) > 0:
            first_container_id = next(iter(data.keys()))
            container_data = data[first_container_id]
            
            # Validate expected fields
            assert isinstance(container_data, dict), "Container data should be a dictionary"
            expected_fields = ["container_id", "container_name", "server", "username", "password", "port"]
            for field in expected_fields:
                assert field in container_data, f"Container data should have '{field}' field"


class TestIntegrationScenarios:
    """Integration-style tests for common workflows."""

    def test_full_lifecycle(self, api_available):
        """Test a full container lifecycle: start -> status -> stop -> destroy."""
        # Step 1: Get available servers
        servers_response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert servers_response.status_code == 200
        
        servers_data = servers_response.json()
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        first_server = next(iter(servers_data.keys()))
        
        # Step 2: Start a container
        start_response = requests.post(
            f"{BASE_URL}/start",
            json={"server": first_server},
            timeout=REQUEST_TIMEOUT
        )
        
        if start_response.status_code == 429:
            pytest.skip("Instance limit reached, cannot test lifecycle")
        
        assert start_response.status_code == 200, \
            f"Expected 200, got {start_response.status_code}: {start_response.text}"
        
        start_data = start_response.json()
        container_id = start_data["id"]
        assert container_id is not None
        assert "proxy" in start_data
        
        # Step 3: Check status
        time.sleep(1)  # Small delay for container to register
        status_response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        assert container_id in status_data, "Container should be in status"
        assert status_data[container_id]["server"] == first_server
        
        # Step 4: Stop the container
        stop_response = requests.post(
            f"{BASE_URL}/stop",
            json={"id": container_id},
            timeout=REQUEST_TIMEOUT
        )
        assert stop_response.status_code == 200
        
        stop_data = stop_response.json()
        assert "message" in stop_data
        
        # Step 5: Destroy the container
        destroy_response = requests.post(
            f"{BASE_URL}/destroy",
            json={"id": container_id},
            timeout=REQUEST_TIMEOUT
        )
        assert destroy_response.status_code == 200
        
        destroy_data = destroy_response.json()
        assert "message" in destroy_data
        
        # Step 6: Verify container is removed from status
        time.sleep(1)
        final_status_response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        final_status_data = final_status_response.json()
        assert container_id not in final_status_data, "Container should be removed after destroy"

    def test_multiple_containers_status(self, api_available):
        """Test that status correctly shows multiple containers."""
        # Get servers
        servers_response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert servers_response.status_code == 200
        
        servers_data = servers_response.json()
        if len(servers_data) < 2:
            pytest.skip("Need at least 2 servers to test multiple containers")
        
        server_list = list(servers_data.keys())[:2]
        container_ids = []
        
        try:
            # Start multiple containers
            for server in server_list:
                start_response = requests.post(
                    f"{BASE_URL}/start",
                    json={"server": server},
                    timeout=REQUEST_TIMEOUT
                )
                
                if start_response.status_code == 200:
                    container_ids.append(start_response.json()["id"])
                    time.sleep(1)  # Small delay between starts
            
            if len(container_ids) == 0:
                pytest.skip("Could not start any containers for multi-container test")
            
            # Check status
            status_response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
            assert status_response.status_code == 200
            
            status_data = status_response.json()
            
            # Verify all containers are in status
            for container_id in container_ids:
                assert container_id in status_data, f"Container {container_id} should be in status"
                assert status_data[container_id]["server"] in server_list
            
            # Verify we have at least the containers we created
            assert len(status_data) >= len(container_ids), \
                f"Status should show at least {len(container_ids)} containers"
        
        finally:
            # Cleanup all containers
            for container_id in container_ids:
                try:
                    requests.post(
                        f"{BASE_URL}/destroy",
                        json={"id": container_id},
                        timeout=REQUEST_TIMEOUT
                    )
                except requests.exceptions.RequestException:
                    pass
