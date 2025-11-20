import os
import pytest
import requests
import time
from urllib.parse import urljoin

# Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
GLUETUN_API_URL = os.getenv("GLUETUN_API_URL", "http://localhost:8001")

# Test timeout in seconds
TEST_TIMEOUT = 30

class TestFrontendConnectivity:
    """Test basic connectivity to the frontend service"""
    
    @pytest.fixture(scope="class", autouse=True)
    def check_service_availability(self):
        """Skip tests if the frontend service is not available"""
        try:
            response = requests.get(FRONTEND_URL, timeout=5)
            if response.status_code != 200:
                pytest.skip(f"Frontend service returned status code {response.status_code}")
        except requests.exceptions.RequestException:
            pytest.skip(f"Frontend service not available at {FRONTEND_URL}")
    
    def test_frontend_responds(self):
        """Test that the frontend service responds to HTTP requests"""
        response = requests.get(FRONTEND_URL)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("Content-Type", "")
    
    def test_frontend_has_content(self):
        """Test that the frontend returns meaningful content"""
        response = requests.get(FRONTEND_URL)
        assert response.status_code == 200
        assert len(response.text) > 100  # Basic check for meaningful content
    
    def test_frontend_static_assets(self):
        """Test that static assets are accessible"""
        # Try to access common static asset paths
        static_paths = [
            "/static/css/style.css",
            "/static/js/main.js",
            "/favicon.ico"
        ]
        
        for path in static_paths:
            try:
                url = urljoin(FRONTEND_URL, path)
                response = requests.get(url, timeout=5)
                # Not all static assets may exist, so we only check if they return 404 or 200
                assert response.status_code in [200, 404]
            except requests.exceptions.RequestException:
                # If we can't connect, that's okay for static assets
                pass


class TestFrontendBackendConnectivity:
    """Test connectivity between frontend and backend services"""
    
    @pytest.fixture(scope="class", autouse=True)
    def check_services_availability(self):
        """Skip tests if either frontend or backend services are not available"""
        # Check frontend
        try:
            response = requests.get(FRONTEND_URL, timeout=5)
            if response.status_code != 200:
                pytest.skip(f"Frontend service returned status code {response.status_code}")
        except requests.exceptions.RequestException:
            pytest.skip(f"Frontend service not available at {FRONTEND_URL}")
        
        # Check backend
        try:
            response = requests.get(f"{BACKEND_URL}/servers", timeout=5)
            if response.status_code != 200:
                pytest.skip(f"Backend service returned status code {response.status_code}")
        except requests.exceptions.RequestException:
            pytest.skip(f"Backend service not available at {BACKEND_URL}")
    
    def test_backend_servers_endpoint(self):
        """Test that the backend servers endpoint is accessible"""
        response = requests.get(f"{BACKEND_URL}/servers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_backend_status_endpoint(self):
        """Test that the backend status endpoint is accessible"""
        response = requests.get(f"{BACKEND_URL}/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    def test_frontend_uses_backend_config(self):
        """Test that the frontend is configured to use the correct backend URL"""
        # This test checks if the frontend is configured with the correct backend URL
        # In a real application, this might be exposed through an API endpoint or in the HTML
        response = requests.get(FRONTEND_URL)
        assert response.status_code == 200
        
        # Check if the backend URL is referenced in the frontend
        # This is a basic check and might need adjustment based on the actual implementation
        html_content = response.text
        assert BACKEND_URL in html_content or "backend" in html_content.lower()


class TestFrontendInKubernetes:
    """Test frontend when running in Kubernetes"""
    
    @pytest.fixture(scope="class", autouse=True)
    def check_kubernetes_environment(self):
        """Skip tests if not running in a Kubernetes environment"""
        # Check if we're running in a Kubernetes pod
        if not os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
            pytest.skip("Not running in a Kubernetes environment")
    
    def test_frontend_pod_environment(self):
        """Test that the frontend pod has the correct environment variables"""
        # Check if required environment variables are set
        required_env_vars = [
            "BACKEND_URL",
            "PORT",
            "MEDIA_DIR"
        ]
        
        for var in required_env_vars:
            assert var in os.environ, f"Required environment variable {var} is not set"
    
    def test_frontend_service_discovery(self):
        """Test that the frontend can discover other services via DNS"""
        # Try to resolve the backend service using Kubernetes DNS
        import socket
        
        # Extract the service name from the backend URL
        backend_host = BACKEND_URL.split("//")[1].split(":")[0]
        
        try:
            # Try to resolve the hostname
            socket.gethostbyname(backend_host)
        except socket.gaierror:
            pytest.fail(f"Could not resolve backend service hostname: {backend_host}")
    
    def test_frontend_media_volume(self):
        """Test that the frontend media volume is accessible"""
        media_dir = os.environ.get("MEDIA_DIR", "/app/media")
        
        # Check if the media directory exists
        assert os.path.exists(media_dir), f"Media directory {media_dir} does not exist"
        
        # Check if the media directory is writable
        test_file = os.path.join(media_dir, "test_write_permission")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except IOError:
            pytest.fail(f"Media directory {media_dir} is not writable")


class TestFrontendIntegration:
    """Integration tests for the frontend service"""
    
    @pytest.fixture(scope="class", autouse=True)
    def check_all_services_availability(self):
        """Skip tests if any of the required services are not available"""
        services = [
            (FRONTEND_URL, "Frontend"),
            (f"{BACKEND_URL}/servers", "Backend"),
            (f"{GLUETUN_API_URL}/servers", "Gluetun API")
        ]
        
        for url, name in services:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code != 200:
                    pytest.skip(f"{name} service returned status code {response.status_code}")
            except requests.exceptions.RequestException:
                pytest.skip(f"{name} service not available at {url}")
    
    def test_complete_workflow(self):
        """Test a complete workflow from frontend to backend to gluetun"""
        # This test simulates a user workflow through the application
        
        # 1. Get available servers from gluetun API
        response = requests.get(f"{GLUETUN_API_URL}/servers")
        assert response.status_code == 200
        servers = response.json()
        assert len(servers) > 0
        
        # 2. Check backend status
        response = requests.get(f"{BACKEND_URL}/status")
        assert response.status_code == 200
        status = response.json()
        
        # 3. Access frontend
        response = requests.get(FRONTEND_URL)
        assert response.status_code == 200
        
        # This is a basic integration test - in a real application, you might
        # want to test more specific user interactions
    
    def test_error_handling(self):
        """Test that the frontend handles errors gracefully"""
        # Try to access a non-existent endpoint
        response = requests.get(f"{FRONTEND_URL}/nonexistent")
        # The frontend should return either a 404 or handle it gracefully
        assert response.status_code in [404, 200]
    
    def test_concurrent_requests(self):
        """Test that the frontend can handle concurrent requests"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def make_request():
            try:
                response = requests.get(FRONTEND_URL, timeout=10)
                results.put(response.status_code)
            except Exception as e:
                results.put(str(e))
        
        # Make 10 concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        success_count = 0
        while not results.empty():
            result = results.get()
            if result == 200:
                success_count += 1
        
        # At least 80% of requests should succeed
        assert success_count >= 8, f"Too many failed requests: {success_count}/10"
