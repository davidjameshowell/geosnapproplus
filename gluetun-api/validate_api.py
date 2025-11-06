#!/usr/bin/env python3
"""
Gluetun API Validation Script

This script validates all endpoints of the Gluetun API by making HTTP requests
and checking responses. It provides detailed output about what's working and what's not.

Usage:
    python validate_api.py [--base-url URL] [--timeout SECONDS]

Example:
    python validate_api.py --base-url http://localhost:8001 --timeout 90
"""

import argparse
import json
import sys
import time
from typing import Dict, Any, Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install it with: pip install requests")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class APIValidator:
    """Validates Gluetun API endpoints."""
    
    def __init__(self, base_url: str, timeout: int = 30, init_timeout: int = 90):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.init_timeout = init_timeout
        self.results = []
        self.created_containers = []
        
    def log(self, message: str, color: str = Colors.RESET):
        """Print a colored message."""
        print(f"{color}{message}{Colors.RESET}")
        
    def log_result(self, endpoint: str, method: str, success: bool, details: str = ""):
        """Log a test result."""
        status = "✓ PASS" if success else "✗ FAIL"
        color = Colors.GREEN if success else Colors.RED
        self.log(f"  {status}: {method} {endpoint}", color)
        if details:
            self.log(f"    {details}", Colors.YELLOW)
        self.results.append({
            "endpoint": endpoint,
            "method": method,
            "success": success,
            "details": details
        })
        
    def check_response(self, response: requests.Response, 
                      expected_status: int = None,
                      require_json: bool = True) -> Tuple[bool, str]:
        """Check if a response is valid."""
        try:
            if expected_status and response.status_code != expected_status:
                return False, f"Expected status {expected_status}, got {response.status_code}"
            
            if require_json:
                try:
                    data = response.json()
                except ValueError:
                    return False, "Response is not valid JSON"
                    
            return True, "OK"
        except Exception as e:
            return False, f"Error checking response: {e}"
    
    def validate_get_servers(self) -> bool:
        """Validate GET /servers endpoint."""
        self.log(f"\n{Colors.BOLD}Testing GET /servers{Colors.RESET}")
        
        try:
            # First request may trigger initialization (can take up to 60s)
            self.log("  Making request (may take up to 60s for initialization)...", Colors.BLUE)
            response = requests.get(f"{self.base_url}/servers", timeout=self.init_timeout)
            
            success, details = self.check_response(response, expected_status=200)
            
            if success:
                data = response.json()
                if not isinstance(data, dict):
                    self.log_result("/servers", "GET", False, "Response is not a dictionary")
                    return False
                    
                server_count = len(data)
                if server_count == 0:
                    self.log_result("/servers", "GET", True, 
                                  "Endpoint works but server list is empty (initialization may have failed)")
                else:
                    # Validate server structure
                    first_key = next(iter(data.keys()))
                    server = data[first_key]
                    if isinstance(server, dict) and "hostname" in server:
                        self.log_result("/servers", "GET", True, 
                                      f"Successfully retrieved {server_count} servers")
                    else:
                        self.log_result("/servers", "GET", True, 
                                      f"Retrieved {server_count} servers (structure may be unexpected)")
            else:
                self.log_result("/servers", "GET", False, details)
                
            return success
            
        except requests.exceptions.Timeout:
            self.log_result("/servers", "GET", False, 
                          f"Request timed out after {self.init_timeout}s")
            return False
        except requests.exceptions.ConnectionError:
            self.log_result("/servers", "GET", False, 
                          f"Could not connect to {self.base_url}")
            return False
        except Exception as e:
            self.log_result("/servers", "GET", False, f"Unexpected error: {e}")
            return False
    
    def validate_post_start(self, test_server: Optional[str] = None) -> Optional[str]:
        """Validate POST /start endpoint. Returns container_id if successful."""
        self.log(f"\n{Colors.BOLD}Testing POST /start{Colors.RESET}")
        
        # Test 1: Missing server parameter
        self.log("  Test 1: Missing server parameter")
        try:
            response = requests.post(
                f"{self.base_url}/start",
                json={},
                timeout=self.timeout
            )
            success, details = self.check_response(response, expected_status=400)
            self.log_result("/start", "POST", success, 
                          f"Missing server: {details} (status: {response.status_code})")
        except Exception as e:
            self.log_result("/start", "POST", False, f"Missing server test error: {e}")
        
        # Test 2: Invalid server
        self.log("  Test 2: Invalid server parameter")
        try:
            response = requests.post(
                f"{self.base_url}/start",
                json={"server": "invalid-server-name-12345"},
                timeout=self.timeout
            )
            success, details = self.check_response(response, expected_status=400)
            if success:
                data = response.json()
                if "error" in data and "invalid" in data["error"].lower():
                    self.log_result("/start", "POST", True, "Correctly rejects invalid server")
                else:
                    self.log_result("/start", "POST", False, "Rejected but error message unexpected")
            else:
                self.log_result("/start", "POST", False, f"Invalid server: {details}")
        except Exception as e:
            self.log_result("/start", "POST", False, f"Invalid server test error: {e}")
        
        # Test 3: Valid server (if available)
        if not test_server:
            # Get available servers
            try:
                servers_response = requests.get(f"{self.base_url}/servers", timeout=self.timeout)
                if servers_response.status_code == 200:
                    servers_data = servers_response.json()
                    if len(servers_data) > 0:
                        test_server = next(iter(servers_data.keys()))
                    else:
                        self.log("  Test 3: Skipped - No servers available", Colors.YELLOW)
                        return None
                else:
                    self.log("  Test 3: Skipped - Could not fetch server list", Colors.YELLOW)
                    return None
            except Exception as e:
                self.log("  Test 3: Skipped - Error fetching servers: {e}", Colors.YELLOW)
                return None
        
        self.log(f"  Test 3: Starting container with server: {test_server}")
        try:
            response = requests.post(
                f"{self.base_url}/start",
                json={"server": test_server},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if "id" in data and "proxy" in data:
                    container_id = data["id"]
                    proxy = data["proxy"]
                    
                    # Validate proxy format
                    if proxy.startswith("http://") and "@localhost:" in proxy:
                        self.log_result("/start", "POST", True, 
                                      f"Successfully started container {container_id}")
                        self.created_containers.append(container_id)
                        return container_id
                    else:
                        self.log_result("/start", "POST", False, 
                                      f"Container started but proxy format invalid")
                else:
                    self.log_result("/start", "POST", False, 
                                    "Response missing 'id' or 'proxy' fields")
                    
            elif response.status_code == 429:
                data = response.json()
                if "error" in data and "limit" in data["error"].lower():
                    self.log_result("/start", "POST", True, 
                                  "Correctly rejects when instance limit reached")
                else:
                    self.log_result("/start", "POST", False, 
                                  "Status 429 but error message unexpected")
            else:
                self.log_result("/start", "POST", False, 
                              f"Unexpected status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/start", "POST", False, f"Error: {e}")
            
        return None
    
    def validate_post_stop(self, container_id: Optional[str] = None) -> bool:
        """Validate POST /stop endpoint."""
        self.log(f"\n{Colors.BOLD}Testing POST /stop{Colors.RESET}")
        
        # Test 1: Missing ID
        self.log("  Test 1: Missing container ID")
        try:
            response = requests.post(
                f"{self.base_url}/stop",
                json={},
                timeout=self.timeout
            )
            success, details = self.check_response(response, expected_status=404)
            self.log_result("/stop", "POST", success, 
                          f"Missing ID: {details} (status: {response.status_code})")
        except Exception as e:
            self.log_result("/stop", "POST", False, f"Missing ID test error: {e}")
        
        # Test 2: Invalid ID
        self.log("  Test 2: Invalid container ID")
        try:
            response = requests.post(
                f"{self.base_url}/stop",
                json={"id": "non-existent-container-id-12345"},
                timeout=self.timeout
            )
            success, details = self.check_response(response, expected_status=404)
            if success:
                data = response.json()
                if "error" in data and "not found" in data["error"].lower():
                    self.log_result("/stop", "POST", True, "Correctly handles invalid container ID")
                else:
                    self.log_result("/stop", "POST", False, "Rejected but error message unexpected")
            else:
                self.log_result("/stop", "POST", False, f"Invalid ID: {details}")
        except Exception as e:
            self.log_result("/stop", "POST", False, f"Invalid ID test error: {e}")
        
        # Test 3: Valid stop (if container available)
        if container_id:
            self.log(f"  Test 3: Stopping container {container_id}")
            try:
                time.sleep(2)  # Give container a moment to be ready
                response = requests.post(
                    f"{self.base_url}/stop",
                    json={"id": container_id},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "message" in data and "stop" in data["message"].lower():
                        self.log_result("/stop", "POST", True, 
                                      f"Successfully stopped container {container_id}")
                        return True
                    else:
                        self.log_result("/stop", "POST", False, 
                                      "Stopped but response message unexpected")
                else:
                    self.log_result("/stop", "POST", False, 
                                  f"Unexpected status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("/stop", "POST", False, f"Error: {e}")
        else:
            self.log("  Test 3: Skipped - No container available to stop", Colors.YELLOW)
        
        return False
    
    def validate_post_destroy(self, container_id: Optional[str] = None) -> bool:
        """Validate POST /destroy endpoint."""
        self.log(f"\n{Colors.BOLD}Testing POST /destroy{Colors.RESET}")
        
        # Test 1: Missing ID
        self.log("  Test 1: Missing container ID")
        try:
            response = requests.post(
                f"{self.base_url}/destroy",
                json={},
                timeout=self.timeout
            )
            success, details = self.check_response(response, expected_status=404)
            self.log_result("/destroy", "POST", success, 
                          f"Missing ID: {details} (status: {response.status_code})")
        except Exception as e:
            self.log_result("/destroy", "POST", False, f"Missing ID test error: {e}")
        
        # Test 2: Invalid ID
        self.log("  Test 2: Invalid container ID")
        try:
            response = requests.post(
                f"{self.base_url}/destroy",
                json={"id": "non-existent-container-id-12345"},
                timeout=self.timeout
            )
            success, details = self.check_response(response, expected_status=404)
            if success:
                data = response.json()
                if "error" in data and "not found" in data["error"].lower():
                    self.log_result("/destroy", "POST", True, "Correctly handles invalid container ID")
                else:
                    self.log_result("/destroy", "POST", False, "Rejected but error message unexpected")
            else:
                self.log_result("/destroy", "POST", False, f"Invalid ID: {details}")
        except Exception as e:
            self.log_result("/destroy", "POST", False, f"Invalid ID test error: {e}")
        
        # Test 3: Valid destroy (if container available)
        if container_id:
            self.log(f"  Test 3: Destroying container {container_id}")
            try:
                response = requests.post(
                    f"{self.base_url}/destroy",
                    json={"id": container_id},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "message" in data and "destroy" in data["message"].lower():
                        self.log_result("/destroy", "POST", True, 
                                      f"Successfully destroyed container {container_id}")
                        if container_id in self.created_containers:
                            self.created_containers.remove(container_id)
                        return True
                    else:
                        self.log_result("/destroy", "POST", False, 
                                      "Destroyed but response message unexpected")
                else:
                    self.log_result("/destroy", "POST", False, 
                                  f"Unexpected status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("/destroy", "POST", False, f"Error: {e}")
        else:
            self.log("  Test 3: Skipped - No container available to destroy", Colors.YELLOW)
        
        return False
    
    def validate_get_status(self) -> bool:
        """Validate GET /status endpoint."""
        self.log(f"\n{Colors.BOLD}Testing GET /status{Colors.RESET}")
        
        try:
            response = requests.get(f"{self.base_url}/status", timeout=self.timeout)
            success, details = self.check_response(response, expected_status=200)
            
            if success:
                data = response.json()
                if not isinstance(data, dict):
                    self.log_result("/status", "GET", False, "Response is not a dictionary")
                    return False
                
                container_count = len(data)
                if container_count > 0:
                    # Validate structure of first container
                    first_id = next(iter(data.keys()))
                    container_data = data[first_id]
                    expected_fields = ["container_id", "container_name", "server", "username", "password", "port"]
                    missing_fields = [f for f in expected_fields if f not in container_data]
                    
                    if missing_fields:
                        self.log_result("/status", "GET", False, 
                                      f"Missing fields in container data: {missing_fields}")
                    else:
                        self.log_result("/status", "GET", True, 
                                      f"Successfully retrieved status for {container_count} container(s)")
                else:
                    self.log_result("/status", "GET", True, "Successfully retrieved status (no running containers)")
            else:
                self.log_result("/status", "GET", False, details)
                
            return success
            
        except Exception as e:
            self.log_result("/status", "GET", False, f"Error: {e}")
            return False
    
    def cleanup_containers(self):
        """Clean up any containers created during validation."""
        if not self.created_containers:
            return
            
        self.log(f"\n{Colors.BOLD}Cleaning up {len(self.created_containers)} container(s)...{Colors.RESET}")
        
        for container_id in self.created_containers[:]:  # Copy list to avoid modification issues
            try:
                # Try destroy first (removes from tracking)
                response = requests.post(
                    f"{self.base_url}/destroy",
                    json={"id": container_id},
                    timeout=self.timeout
                )
                if response.status_code == 200:
                    self.log(f"  ✓ Destroyed container {container_id}", Colors.GREEN)
                else:
                    # Try stop if destroy failed
                    response = requests.post(
                        f"{self.base_url}/stop",
                        json={"id": container_id},
                        timeout=self.timeout
                    )
                    if response.status_code == 200:
                        self.log(f"  ✓ Stopped container {container_id}", Colors.YELLOW)
                    else:
                        self.log(f"  ✗ Failed to clean up container {container_id}", Colors.RED)
            except Exception as e:
                self.log(f"  ✗ Error cleaning up container {container_id}: {e}", Colors.RED)
        
        self.created_containers.clear()
    
    def run_all_validation(self) -> Dict[str, Any]:
        """Run all validation tests and return summary."""
        self.log(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
        self.log(f"{Colors.BOLD}Gluetun API Validation{Colors.RESET}")
        self.log(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
        self.log(f"Base URL: {self.base_url}")
        self.log(f"Timeout: {self.timeout}s (regular), {self.init_timeout}s (initialization)")
        
        # Validate endpoints in order
        get_servers_ok = self.validate_get_servers()
        
        container_id = None
        if get_servers_ok:
            container_id = self.validate_post_start()
        
        # For stop/destroy tests, use the container we just created
        # If we don't have one, still test error cases
        if container_id:
            # Stop the container
            self.validate_post_stop(container_id)
            # Then destroy it (after stop)
            self.validate_post_destroy(container_id)
        else:
            # Test error cases only
            self.validate_post_stop()
            self.validate_post_destroy()
        
        self.validate_get_status()
        
        # Cleanup any remaining containers
        self.cleanup_containers()
        
        # Print summary
        self.print_summary()
        
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r["success"]),
            "failed": sum(1 for r in self.results if not r["success"]),
            "results": self.results
        }
    
    def print_summary(self):
        """Print validation summary."""
        self.log(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
        self.log(f"{Colors.BOLD}Validation Summary{Colors.RESET}")
        self.log(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
        
        passed = sum(1 for r in self.results if r["success"])
        failed = sum(1 for r in self.results if not r["success"])
        total = len(self.results)
        
        self.log(f"Total tests: {total}")
        self.log(f"{Colors.GREEN}Passed: {passed}{Colors.RESET}")
        if failed > 0:
            self.log(f"{Colors.RED}Failed: {failed}{Colors.RESET}")
        
        if failed > 0:
            self.log(f"\n{Colors.BOLD}Failed Tests:{Colors.RESET}")
            for result in self.results:
                if not result["success"]:
                    self.log(f"  ✗ {result['method']} {result['endpoint']}", Colors.RED)
                    if result["details"]:
                        self.log(f"    {result['details']}", Colors.YELLOW)
        
        self.log(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Gluetun API endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_api.py
  python validate_api.py --base-url http://localhost:8001
  python validate_api.py --base-url http://localhost:8001 --timeout 60 --init-timeout 120
        """
    )
    
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Base URL of the Gluetun API (default: http://localhost:8001)"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout for regular requests in seconds (default: 30)"
    )
    
    parser.add_argument(
        "--init-timeout",
        type=int,
        default=90,
        help="Timeout for initialization request in seconds (default: 90)"
    )
    
    args = parser.parse_args()
    
    validator = APIValidator(
        base_url=args.base_url,
        timeout=args.timeout,
        init_timeout=args.init_timeout
    )
    
    summary = validator.run_all_validation()
    
    # Exit with appropriate code
    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

