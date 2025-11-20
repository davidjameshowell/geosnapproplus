#!/usr/bin/env python3
"""
Example usage of the Gluetun Kubernetes API

This script demonstrates how to interact with the Gluetun K8s API
to create and manage VPN pods programmatically.
"""

import requests
import time
import sys

# Configuration
API_URL = "http://localhost:30801"


def check_health():
    """Check if the API is healthy."""
    print("Checking API health...")
    response = requests.get(f"{API_URL}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ API is healthy. Servers loaded: {data.get('servers_loaded', False)}")
        return True
    else:
        print(f"✗ API health check failed: {response.status_code}")
        return False


def list_servers(country=None, city=None):
    """List available VPN servers."""
    print(f"\nListing servers (country={country}, city={city})...")
    params = {}
    if country:
        params['country'] = country
    if city:
        params['city'] = city
    
    response = requests.get(f"{API_URL}/servers", params=params)
    if response.status_code == 200:
        servers = response.json()
        print(f"✓ Found {len(servers)} servers")
        
        # Show first few servers
        for i, (key, server) in enumerate(list(servers.items())[:3]):
            print(f"  - {server.get('country')}, {server.get('city')}: {server.get('hostname')}")
        
        if len(servers) > 3:
            print(f"  ... and {len(servers) - 3} more")
        
        return servers
    else:
        print(f"✗ Failed to list servers: {response.status_code}")
        return {}


def get_locations():
    """Get hierarchical location data."""
    print("\nGetting location data...")
    response = requests.get(f"{API_URL}/locations")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Found {data['total_countries']} countries, "
              f"{data['total_cities']} cities, "
              f"{data['total_servers']} servers")
        
        # Show first few countries
        for country in data['countries'][:3]:
            print(f"  - {country['name']}: {country['total_servers']} servers in {country['city_count']} cities")
        
        return data
    else:
        print(f"✗ Failed to get locations: {response.status_code}")
        return {}


def start_vpn_pod(country="USA", city=None):
    """Start a VPN pod."""
    print(f"\nStarting VPN pod (country={country}, city={city})...")
    payload = {"country": country}
    if city:
        payload["city"] = city
    
    response = requests.post(f"{API_URL}/start", json=payload, timeout=120)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ VPN pod started successfully!")
        print(f"  - Pod ID: {data['id']}")
        print(f"  - Pod Name: {data['pod_name']}")
        print(f"  - Pod IP: {data['pod_ip']}")
        print(f"  - Proxy: {data['proxy']}")
        return data
    elif response.status_code == 429:
        print(f"✗ Instance limit reached")
        return None
    else:
        print(f"✗ Failed to start VPN pod: {response.status_code}")
        print(f"  Error: {response.text}")
        return None


def get_status():
    """Get status of all running pods."""
    print("\nGetting pod status...")
    response = requests.get(f"{API_URL}/status")
    if response.status_code == 200:
        pods = response.json()
        print(f"✓ {len(pods)} VPN pods running")
        
        for pod_id, pod_info in pods.items():
            print(f"  - {pod_info['pod_name']} ({pod_info['status']})")
            print(f"    Server: {pod_info['server']}")
            print(f"    IP: {pod_info['pod_ip']}")
        
        return pods
    else:
        print(f"✗ Failed to get status: {response.status_code}")
        return {}


def destroy_vpn_pod(pod_id):
    """Destroy a VPN pod."""
    print(f"\nDestroying VPN pod {pod_id}...")
    response = requests.post(f"{API_URL}/destroy", json={"id": pod_id})
    if response.status_code == 200:
        print(f"✓ VPN pod destroyed successfully")
        return True
    elif response.status_code == 404:
        print(f"✗ Pod not found")
        return False
    else:
        print(f"✗ Failed to destroy pod: {response.status_code}")
        return False


def test_proxy(proxy_url):
    """Test the proxy connection (requires access to pod network)."""
    print(f"\nTesting proxy: {proxy_url}")
    print("Note: This requires network access to the pod IP address")
    
    try:
        # This will only work if running from within the Kubernetes cluster
        # or if you have network access to the pod network
        response = requests.get(
            "http://ifconfig.me",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=10
        )
        if response.status_code == 200:
            print(f"✓ Proxy works! External IP: {response.text}")
            return True
        else:
            print(f"✗ Proxy test failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Cannot test proxy from this network location")
        print(f"  (This is normal if running outside the cluster)")
        print(f"  Error: {e}")
        return False


def main():
    """Main demonstration flow."""
    print("=" * 60)
    print("Gluetun Kubernetes API - Example Usage")
    print("=" * 60)
    
    # Step 1: Health check
    if not check_health():
        print("\n✗ API is not available. Make sure the service is running.")
        sys.exit(1)
    
    # Step 2: List locations
    locations = get_locations()
    
    # Step 3: List servers
    servers = list_servers(country="USA")
    
    if not servers:
        print("\n✗ No servers available. Cannot continue.")
        sys.exit(1)
    
    # Step 4: Start a VPN pod
    vpn_pod = start_vpn_pod(country="USA")
    
    if not vpn_pod:
        print("\n✗ Failed to start VPN pod. Checking existing pods...")
        get_status()
        sys.exit(1)
    
    pod_id = vpn_pod['id']
    proxy_url = vpn_pod['proxy']
    
    # Step 5: Wait a moment
    print("\nWaiting 5 seconds for pod to stabilize...")
    time.sleep(5)
    
    # Step 6: Check status
    get_status()
    
    # Step 7: Test proxy (optional, may fail if not in cluster)
    test_proxy(proxy_url)
    
    # Step 8: Clean up
    input("\nPress Enter to destroy the VPN pod and exit...")
    destroy_vpn_pod(pod_id)
    
    # Step 9: Verify cleanup
    print("\nFinal status check:")
    get_status()
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

