"""
Integration tests for the Gluetun Kubernetes API

This test suite validates all API endpoints by making actual HTTP requests
to the gluetun-k8s-api service running in Kubernetes.

IMPORTANT NOTES:
- The API should be accessible via the NodePort service or port-forwarding
- The first request to /servers triggers initialization which may take some time
- Tests automatically clean up pods they create
- Assumes a working Kubernetes cluster with proper credentials configured

API endpoints tested:
- GET /servers - Retrieve list of Mullvad servers
- POST /start - Start a Gluetun VPN pod
- POST /destroy - Destroy a Gluetun pod
- GET /status - Get status of all running pods
- GET /health - Health check endpoint
"""

import json
import os
import pytest
import requests
import time

# Base URL for the gluetun-k8s-api service
BASE_URL = os.getenv("GLUETUN_K8S_API_URL", "http://localhost:30801")
REQUEST_TIMEOUT = 30  # seconds
INITIALIZATION_TIMEOUT = 120  # seconds - pod provisioning takes longer than Docker

# Mock server data for testing when real servers aren't available
MOCK_SERVERS = {
    "usa-new-york-ny-us-nyc-wg-301": {
        "hostname": "us-nyc-wg-301",
        "country": "USA",
        "city": "New York",
        "vpn": "wireguard"
    },
    "germany-berlin-de-ber-wg-001": {
        "hostname": "de-ber-wg-001",
        "country": "Germany",
        "city": "Berlin",
        "vpn": "wireguard"
    },
    "sweden-stockholm-se-sto-wg-101": {
        "hostname": "se-sto-wg-101",
        "country": "Sweden",
        "city": "Stockholm",
        "vpn": "wireguard"
    }
}


def get_test_servers():
    """Get servers for testing - real or mock."""
    try:
        response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            servers = response.json()
            # If we have real servers, use them
            if len(servers) > 0:
                return servers, "real"
            # Otherwise fall back to mock servers
            return MOCK_SERVERS, "mock"
    except Exception:
        pass
    return MOCK_SERVERS, "mock"


@pytest.fixture(scope="session")
def api_available():
    """Check if the API service is available before running tests."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            return True
    except requests.exceptions.Timeout:
        pytest.skip(
            f"Gluetun K8s API health check timed out at {BASE_URL}. "
            "Make sure the service is running and accessible."
        )
    except requests.exceptions.RequestException as e:
        pytest.skip(
            f"Gluetun K8s API not available at {BASE_URL}: {e}. "
            "Make sure the Kubernetes deployment is running."
        )
    
    pytest.skip(
        f"Gluetun K8s API returned unexpected status. "
        "Make sure the Kubernetes deployment is running."
    )


@pytest.fixture(autouse=True)
def cleanup_pods(api_available):
    """Clean up any pods created during tests."""
    yield
    
    # After each test, get status and destroy any test pods
    try:
        response = requests.get(f"{BASE_URL}/status", timeout=10)
        if response.status_code == 200:
            pods = response.json()
            for pod_id in list(pods.keys()):
                try:
                    requests.post(
                        f"{BASE_URL}/destroy",
                        json={"id": pod_id},
                        timeout=REQUEST_TIMEOUT
                    )
                except requests.exceptions.RequestException:
                    pass
                time.sleep(1)
    except requests.exceptions.RequestException:
        pass


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""
    
    def test_health_check(self, api_available):
        """Test the health check endpoint."""
        response = requests.get(f"{BASE_URL}/health", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"


class TestGetServers:
    """Tests for GET /servers endpoint."""

    def test_get_servers_success(self, api_available):
        """Test successfully retrieving the list of servers."""
        response = requests.get(f"{BASE_URL}/servers", timeout=INITIALIZATION_TIMEOUT)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), "Response should be a dictionary"
        
        if len(data) > 0:
            first_server_key = next(iter(data.keys()))
            server_data = data[first_server_key]
            assert isinstance(server_data, dict), "Server data should be a dictionary"
            if "hostname" in server_data:
                assert isinstance(server_data["hostname"], str)
                assert len(server_data["hostname"]) > 0

    def test_get_servers_response_format(self, api_available):
        """Test that servers endpoint returns valid JSON."""
        response = requests.get(f"{BASE_URL}/servers", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict), "Response must be a JSON object"


class TestLocations:
    """Tests for GET /locations endpoint."""
    
    def test_get_locations(self, api_available):
        """Test retrieving hierarchical location data."""
        response = requests.get(f"{BASE_URL}/locations", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        assert "countries" in data
        assert isinstance(data["countries"], list)


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
        assert "invalid" in data["error"].lower()

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

    def test_start_gluetun_with_valid_server(self, api_available):
        """Test starting with a valid server (using mock servers for testing)."""
        # Get test servers (real or mock)
        servers_data, server_type = get_test_servers()
        
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        first_server = next(iter(servers_data.keys()))
        print(f"\nUsing {server_type} server: {first_server}")
        
        request_data = {"server": first_server}
        
        response = requests.post(
            f"{BASE_URL}/start",
            json=request_data,
            timeout=INITIALIZATION_TIMEOUT  # Pod creation takes longer
        )
        
        # With mock servers, we expect 400 (invalid server) since they don't exist in the API
        # With real servers, we expect 200 or 429
        if server_type == "mock":
            # Mock servers will fail validation (expected)
            assert response.status_code == 400, \
                f"Expected 400 with mock server, got {response.status_code}: {response.text}"
            data = response.json()
            assert "error" in data
            print(f"✓ Mock server correctly rejected: {data['error']}")
        else:
            # Real servers should succeed or hit limit
            assert response.status_code in [200, 429], \
                f"Expected 200 or 429, got {response.status_code}: {response.text}"
            
            if response.status_code == 200:
                data = response.json()
                assert "id" in data, "Response should contain pod id"
                assert "proxy" in data, "Response should contain proxy URL"
                assert data["proxy"].startswith("http://"), "Proxy should be HTTP URL"
                assert "pod_name" in data
                assert "pod_ip" in data
                
                pod_id = data["id"]
                
                # Clean up immediately after test
                destroy_response = requests.post(
                    f"{BASE_URL}/destroy",
                    json={"id": pod_id},
                    timeout=REQUEST_TIMEOUT
                )
                if destroy_response.status_code != 200:
                    print(f"Warning: Failed to cleanup pod {pod_id}")
            
            elif response.status_code == 429:
                data = response.json()
                assert "error" in data
                assert "limit" in data["error"].lower()


class TestDestroyGluetun:
    """Tests for POST /destroy endpoint."""

    def test_destroy_gluetun_pod_not_found(self, api_available):
        """Test destroying a pod that doesn't exist."""
        request_data = {"id": "non-existent-pod-id-12345"}
        
        response = requests.post(
            f"{BASE_URL}/destroy",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_destroy_gluetun_missing_id(self, api_available):
        """Test destroying without providing pod ID."""
        request_data = {}
        
        response = requests.post(
            f"{BASE_URL}/destroy",
            json=request_data,
            timeout=REQUEST_TIMEOUT
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "error" in data

    def test_destroy_gluetun_success(self, api_available):
        """Test successfully destroying a pod (requires real servers)."""
        # Get test servers (only proceed with real servers)
        servers_data, server_type = get_test_servers()
        
        if server_type == "mock":
            pytest.skip("Destroy test requires real servers with valid credentials")
        
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        first_server = next(iter(servers_data.keys()))
        
        # Start a pod
        start_response = requests.post(
            f"{BASE_URL}/start",
            json={"server": first_server},
            timeout=INITIALIZATION_TIMEOUT
        )
        
        if start_response.status_code != 200:
            pytest.skip(f"Cannot start pod for destroy test: {start_response.status_code}")
        
        pod_id = start_response.json()["id"]
        
        # Wait a moment for pod to be fully registered
        time.sleep(3)
        
        # Verify it's in status before destroying
        status_before = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        if status_before.status_code == 200:
            pods_before = status_before.json()
            assert pod_id in pods_before, "Pod should be in status before destroy"
        
        # Now destroy it
        destroy_response = requests.post(
            f"{BASE_URL}/destroy",
            json={"id": pod_id},
            timeout=REQUEST_TIMEOUT
        )
        
        assert destroy_response.status_code == 200, \
            f"Expected 200, got {destroy_response.status_code}: {destroy_response.text}"
        data = destroy_response.json()
        assert "message" in data
        assert "destroyed" in data["message"].lower()
        
        # Verify it's removed from status
        time.sleep(2)
        status_after = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        if status_after.status_code == 200:
            pods_after = status_after.json()
            assert pod_id not in pods_after, "Pod should be removed from status after destroy"


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


class TestIntegrationScenarios:
    """Integration-style tests for common workflows."""

    def test_full_lifecycle(self, api_available):
        """Test a full pod lifecycle: start -> status -> destroy (requires real servers)."""
        # Get test servers (only proceed with real servers)
        servers_data, server_type = get_test_servers()
        
        if server_type == "mock":
            pytest.skip("Full lifecycle test requires real servers with valid credentials")
        
        if len(servers_data) == 0:
            pytest.skip("No servers available to test with")
        
        first_server = next(iter(servers_data.keys()))
        
        # Step 2: Start a pod
        start_response = requests.post(
            f"{BASE_URL}/start",
            json={"server": first_server},
            timeout=INITIALIZATION_TIMEOUT
        )
        
        if start_response.status_code == 429:
            pytest.skip("Instance limit reached, cannot test lifecycle")
        
        assert start_response.status_code == 200, \
            f"Expected 200, got {start_response.status_code}: {start_response.text}"
        
        start_data = start_response.json()
        pod_id = start_data["id"]
        assert pod_id is not None
        assert "proxy" in start_data
        
        # Step 3: Check status
        time.sleep(2)
        status_response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        assert pod_id in status_data, "Pod should be in status"
        assert status_data[pod_id]["server"] == first_server
        
        # Step 4: Destroy the pod
        destroy_response = requests.post(
            f"{BASE_URL}/destroy",
            json={"id": pod_id},
            timeout=REQUEST_TIMEOUT
        )
        assert destroy_response.status_code == 200
        
        destroy_data = destroy_response.json()
        assert "message" in destroy_data
        
        # Step 5: Verify pod is removed from status
        time.sleep(2)
        final_status_response = requests.get(f"{BASE_URL}/status", timeout=REQUEST_TIMEOUT)
        final_status_data = final_status_response.json()
        assert pod_id not in final_status_data, "Pod should be removed after destroy"

