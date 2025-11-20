"""
End-to-end smoke tests that exercise the deployed stack inside the Kind cluster.

These tests deploy the UNIFIED GeoSnappro Helm chart (charts/geosnappro), 
set up port forwarding, and validate all services are functioning correctly.

The unified chart deploys:
- Screenshot API (port 8000)
- Gluetun API (port 8001)  
- Frontend (port 5000)

All three services are deployed together from a single Helm chart.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Dict

import pytest
import requests

NAMESPACE = os.environ.get("E2E_NAMESPACE", "geosnap-e2e")
RELEASE_NAME = os.environ.get("E2E_RELEASE_NAME", "geosnappro-e2e")
CHART_PATH = os.environ.get("E2E_CHART_PATH", str(Path(__file__).parent.parent / "charts" / "geosnappro"))
PORT_FORWARD_TIMEOUT = int(os.environ.get("E2E_PORT_FORWARD_TIMEOUT", "60"))
HTTP_TIMEOUT = int(os.environ.get("E2E_HTTP_TIMEOUT", "120"))
POLL_INTERVAL = float(os.environ.get("E2E_POLL_INTERVAL", "2.0"))
HELM_INSTALL_TIMEOUT = int(os.environ.get("E2E_HELM_INSTALL_TIMEOUT", "300"))

# Port forward targets - using service names from unified chart
# Format: (k8s_resource, local_port, remote_port, key_name)
# Service names use fullnameOverride from values.yaml to be simple names
PORT_FORWARD_TARGETS = (
    ("svc/gluetun-api", 28081, 8001, "gluetun"),        # Gluetun API service
    ("svc/screenshot-api", 28080, 8000, "screenshot"),  # Screenshot API service
    ("svc/frontend", 5000, 5000, "frontend"),           # Frontend service on port 5000
)


def _run_command(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess command and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _create_namespace() -> None:
    """Create the Kubernetes namespace if it doesn't exist."""
    result = _run_command(["kubectl", "get", "namespace", NAMESPACE])
    if result.returncode != 0:
        print(f"Creating namespace {NAMESPACE}...")
        result = _run_command(["kubectl", "create", "namespace", NAMESPACE])
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create namespace: {result.stderr}")


def _create_wireguard_secret() -> None:
    """Create WireGuard credentials secret for gluetun-api."""
    # Check if secret already exists
    result = _run_command([
        "kubectl", "get", "secret", "gluetun-wireguard-credentials",
        "-n", NAMESPACE
    ])
    
    if result.returncode == 0:
        print("WireGuard secret already exists, skipping creation...")
        return
    
    # Use example credentials from docker-compose.yml
    print("Creating WireGuard credentials secret...")
    result = _run_command([
        "kubectl", "create", "secret", "generic", "gluetun-wireguard-credentials",
        "--from-literal=wireguard-private-key=aCv31OvwOxhL7SzeSIAiQm1nXPw/pPNi+HPMj9rcxG8=",
        "--from-literal=wireguard-addresses=10.68.50.98/32",
        "-n", NAMESPACE
    ])
    
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create secret: {result.stderr}")


def _deploy_helm_chart() -> None:
    """
    Deploy the unified GeoSnappro Helm chart.
    
    This deploys all three services (screenshot-api, gluetun-api, frontend) 
    from a single chart located at charts/geosnappro/.
    """
    chart_path = Path(CHART_PATH)
    if not chart_path.exists():
        raise FileNotFoundError(f"Unified Helm chart not found at {chart_path}")
    
    print(f"\n{'=' * 80}")
    print(f"Deploying UNIFIED GeoSnappro Helm Chart")
    print(f"{'=' * 80}")
    print(f"Chart path: {chart_path}")
    print(f"Release name: {RELEASE_NAME}")
    print(f"Namespace: {NAMESPACE}")
    print(f"This will deploy: screenshot-api, gluetun-api, and frontend")
    print(f"{'=' * 80}\n")
    
    # Check if release already exists
    result = _run_command([
        "helm", "list", "-n", NAMESPACE, "-q"
    ])
    
    if RELEASE_NAME in result.stdout:
        print(f"Release {RELEASE_NAME} already exists, upgrading...")
        cmd = [
            "helm", "upgrade", RELEASE_NAME, str(chart_path),
            "--namespace", NAMESPACE,
            "--wait",
            "--timeout", f"{HELM_INSTALL_TIMEOUT}s",
        ]
    else:
        print(f"Installing release {RELEASE_NAME}...")
        cmd = [
            "helm", "install", RELEASE_NAME, str(chart_path),
            "--namespace", NAMESPACE,
            "--create-namespace",
            "--wait",
            "--timeout", f"{HELM_INSTALL_TIMEOUT}s",
        ]
    
    result = _run_command(cmd, timeout=HELM_INSTALL_TIMEOUT + 30)
    
    if result.returncode != 0:
        print(f"Helm command failed with exit code {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"Failed to deploy Helm chart: {result.stderr}")
    
    print("Helm chart deployed successfully!")
    print(result.stdout)


def _wait_for_pods_ready(timeout: int = 300) -> None:
    """Wait for all pods in the namespace to be ready."""
    print(f"Waiting for pods to be ready in namespace {NAMESPACE}...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = _run_command([
            "kubectl", "get", "pods",
            "-n", NAMESPACE,
            "-l", f"app.kubernetes.io/instance={RELEASE_NAME}",
            "-o", "jsonpath={.items[*].status.conditions[?(@.type=='Ready')].status}"
        ])
        
        if result.returncode == 0:
            statuses = result.stdout.strip().split()
            if statuses and all(s == "True" for s in statuses):
                print("All pods are ready!")
                return
        
        time.sleep(5)
    
    # Print pod status for debugging
    result = _run_command([
        "kubectl", "get", "pods", "-n", NAMESPACE
    ])
    print(f"Pod status:\n{result.stdout}")
    
    raise TimeoutError(f"Timed out waiting for pods to be ready in namespace {NAMESPACE}")


def _undeploy_helm_chart() -> None:
    """Uninstall the Helm chart."""
    print(f"Uninstalling Helm release {RELEASE_NAME}...")
    result = _run_command([
        "helm", "uninstall", RELEASE_NAME,
        "--namespace", NAMESPACE
    ], timeout=60)
    
    if result.returncode != 0 and "not found" not in result.stderr:
        print(f"Warning: Failed to uninstall chart: {result.stderr}")


def _wait_for_port(host: str, port: int, timeout: int) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for port {host}:{port}")


def _start_port_forward(resource: str, local_port: int, remote_port: int) -> subprocess.Popen:
    cmd = [
        "kubectl",
        "port-forward",
        "-n",
        NAMESPACE,
        resource,
        f"{local_port}:{remote_port}",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_port("127.0.0.1", local_port, PORT_FORWARD_TIMEOUT)
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        raise
    return proc


@pytest.fixture(scope="session")
def helm_deployment() -> None:
    """
    Session-scoped fixture to deploy the UNIFIED Helm chart before tests run.
    
    This fixture:
    1. Creates the namespace
    2. Creates WireGuard credentials secret
    3. Deploys the unified chart (charts/geosnappro)
    4. Waits for all pods to be ready
    5. Automatically cleans up after tests complete
    
    The unified chart deploys: screenshot-api, gluetun-api, and frontend.
    """
    print("\n" + "=" * 80)
    print("🚀 Setting up GeoSnappro E2E Test Environment")
    print("=" * 80)
    print("📦 Deploying UNIFIED Helm Chart (all services in one chart)")
    print("=" * 80 + "\n")
    
    try:
        # Step 1: Create namespace
        print("Step 1/4: Creating namespace...")
        _create_namespace()
        print(f"✅ Namespace '{NAMESPACE}' ready\n")
        
        # Step 2: Create WireGuard secret
        print("Step 2/4: Setting up WireGuard credentials...")
        _create_wireguard_secret()
        print("✅ WireGuard secret created\n")
        
        # Step 3: Deploy Helm chart
        print("Step 3/4: Deploying unified Helm chart...")
        _deploy_helm_chart()
        print("✅ Helm chart deployed\n")
        
        # Step 4: Wait for pods to be ready
        print("Step 4/4: Waiting for all pods to be ready...")
        _wait_for_pods_ready(timeout=HELM_INSTALL_TIMEOUT)
        print("✅ All pods are ready\n")
        
        print("\n" + "=" * 80)
        print("✅ GeoSnappro E2E Environment Ready!")
        print("=" * 80)
        print("📦 Unified chart deployed with:")
        print("   • Screenshot API (port 8000)")
        print("   • Gluetun API (port 8001)")
        print("   • Frontend (port 5000)")
        print("=" * 80 + "\n")
        
        yield
        
    finally:
        # Cleanup
        print("\n" + "=" * 80)
        print("🧹 Cleaning up GeoSnappro E2E Test Environment")
        print("=" * 80)
        
        if os.environ.get("E2E_SKIP_CLEANUP", "").lower() not in ("true", "1", "yes"):
            _undeploy_helm_chart()
            print("✅ Cleanup complete!")
        else:
            print("⚠️  Cleanup skipped (E2E_SKIP_CLEANUP is set)")
            print(f"   To clean up manually, run:")
            print(f"   helm uninstall {RELEASE_NAME} -n {NAMESPACE}")
        
        print("=" * 80 + "\n")


@pytest.fixture(scope="session")
def port_forwards(helm_deployment: None) -> Dict[str, Dict[str, int]]:
    """
    Set up port forwarding for all services deployed by the unified chart.
    
    This creates local access to:
    - Gluetun API (port 28081 -> 8001)
    - Screenshot API (port 28080 -> 8000)
    - Frontend (port 5000 -> 5000)
    """
    forwards = {}
    managed_processes: Dict[str, subprocess.Popen] = {}
    
    print(f"\n{'=' * 80}")
    print(f"🔌 Setting up Port Forwarding for Unified Chart Services")
    print(f"{'=' * 80}")
    
    try:
        for resource, local_port, remote_port, key in PORT_FORWARD_TARGETS:
            print(f"Port forwarding: {resource} -> 127.0.0.1:{local_port}")
            proc = _start_port_forward(resource, local_port, remote_port)
            forwards[key] = {"port": local_port}
            managed_processes[key] = proc
            time.sleep(0.2)  # brief pause to stabilise connection
        
        print(f"\n✅ Port Forwarding Active!")
        print(f"{'=' * 80}")
        print(f"Access Services:")
        print(f"  • Frontend:       http://127.0.0.1:5000")
        print(f"  • Screenshot API: http://127.0.0.1:28080")
        print(f"  • Gluetun API:    http://127.0.0.1:28081")
        print(f"{'=' * 80}\n")
        
        yield forwards
    finally:
        print(f"\n{'=' * 80}")
        print(f"🔌 Cleaning up port forwards...")
        print(f"{'=' * 80}\n")
        for proc in managed_processes.values():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()


def _wait_for_http_ok(url: str, timeout: int) -> requests.Response:
    deadline = time.time() + timeout
    last_exception: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code < 500:
                return response
        except requests.RequestException as exc:  # pragma: no cover - best effort logging
            last_exception = exc
        time.sleep(POLL_INTERVAL)
    if last_exception:
        raise AssertionError(f"Timed out waiting for {url}: {last_exception}") from last_exception
    raise AssertionError(f"Timed out waiting for {url}")


@pytest.fixture(scope="session")
def endpoints(port_forwards: Dict[str, Dict[str, int]]) -> Dict[str, str]:
    return {
        name: f"http://127.0.0.1:{spec['port']}"
        for name, spec in port_forwards.items()
    }


def test_gluetun_health(endpoints: Dict[str, str]) -> None:
    url = f"{endpoints['gluetun']}/health"
    response = _wait_for_http_ok(url, HTTP_TIMEOUT)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "healthy"
    assert "servers_loaded" in payload


def test_gluetun_servers_preloaded(endpoints: Dict[str, str]) -> None:
    url = f"{endpoints['gluetun']}/servers"
    response = _wait_for_http_ok(url, HTTP_TIMEOUT)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data, "Expected preloaded Mullvad servers to be available"


def test_screenshot_api_health(endpoints: Dict[str, str]) -> None:
    url = f"{endpoints['screenshot']}/health"
    response = _wait_for_http_ok(url, HTTP_TIMEOUT)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "healthy"
    assert payload.get("service") == "Playwright API"


def test_frontend_homepage(endpoints: Dict[str, str]) -> None:
    """
    Test that the frontend homepage loads correctly on port 5000.
    
    This validates the unified chart's frontend deployment and provides
    a URL for manual validation in your browser.
    """
    url = endpoints["frontend"]
    print(f"\n{'=' * 80}")
    print(f"🌐 Testing Frontend from Unified Chart")
    print(f"{'=' * 80}")
    print(f"Frontend URL: {url}")
    print(f"Port: 5000 (as configured in unified chart)")
    print(f"{'=' * 80}\n")
    
    response = _wait_for_http_ok(url, HTTP_TIMEOUT)
    assert response.status_code == 200
    body = response.text
    assert "Capture Any Website" in body
    assert "Create New Task" in body
    
    print(f"\n{'=' * 80}")
    print(f"✅ Frontend Validation Successful!")
    print(f"{'=' * 80}")
    print(f"Frontend is accessible at: {url}")
    print(f"")
    print(f"📋 Manual Validation Steps:")
    print(f"   1. Open your browser")
    print(f"   2. Navigate to: {url}")
    print(f"   3. You should see the 'Capture Any Website' interface")
    print(f"   4. Verify you can interact with the UI")
    print(f"")
    print(f"💡 This frontend was deployed from the unified Helm chart")
    print(f"   Location: charts/geosnappro/")
    print(f"{'=' * 80}\n")


def test_frontend_port_5000_accessibility(port_forwards: Dict[str, Dict[str, int]]) -> None:
    """Verify that frontend is accessible on the expected port 5000."""
    frontend_port = port_forwards["frontend"]["port"]
    assert frontend_port == 5000, f"Expected frontend on port 5000, got {frontend_port}"
    
    # Verify port is actually listening
    url = f"http://127.0.0.1:{frontend_port}"
    response = requests.get(url, timeout=10)
    assert response.status_code == 200
    
    print(f"\n✅ Frontend successfully validated on port {frontend_port}")
    print(f"   Access at: {url}\n")


def test_unified_chart_all_services_deployed() -> None:
    """
    Verify that all three services from the unified chart are deployed.
    
    This test ensures the unified Helm chart deployed all expected components:
    - screenshot-api
    - gluetun-api
    - frontend
    """
    print(f"\n{'=' * 80}")
    print(f"🔍 Validating Unified Chart Deployment")
    print(f"{'=' * 80}")
    print(f"Checking all services from unified chart are present...")
    print(f"{'=' * 80}\n")
    
    # Get all deployments in the namespace
    result = _run_command([
        "kubectl", "get", "deployments",
        "-n", NAMESPACE,
        "-l", f"app.kubernetes.io/instance={RELEASE_NAME}",
        "-o", "jsonpath={.items[*].metadata.name}"
    ])
    
    assert result.returncode == 0, f"Failed to get deployments: {result.stderr}"
    deployments = result.stdout.strip().split()
    
    print(f"Found deployments: {', '.join(deployments)}")
    
    # Verify all three services are present
    expected_services = ["screenshot-api", "gluetun-api", "frontend"]
    for service in expected_services:
        # Check if any deployment name contains the service name
        found = any(service in dep for dep in deployments)
        assert found, f"Service '{service}' not found in deployments: {deployments}"
        print(f"  ✅ {service} - deployed")
    
    # Get all services
    result = _run_command([
        "kubectl", "get", "services",
        "-n", NAMESPACE,
        "-l", f"app.kubernetes.io/instance={RELEASE_NAME}",
        "-o", "jsonpath={.items[*].metadata.name}"
    ])
    
    assert result.returncode == 0, f"Failed to get services: {result.stderr}"
    services = result.stdout.strip().split()
    
    print(f"\nFound services: {', '.join(services)}")
    
    for service in expected_services:
        found = any(service in svc for svc in services)
        assert found, f"Service '{service}' not found in services: {services}"
        print(f"  ✅ {service} - service created")
    
    print(f"\n{'=' * 80}")
    print(f"✅ Unified Chart Validation Complete!")
    print(f"{'=' * 80}")
    print(f"All three services from the unified chart are deployed successfully:")
    print(f"  • Screenshot API")
    print(f"  • Gluetun API")
    print(f"  • Frontend")
    print(f"{'=' * 80}\n")


