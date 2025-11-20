import docker
import json
import logging
import os
import random
import string
import time
import uuid
import requests

from flask import Flask, jsonify, request
from flask_cors import CORS

import config

# Configure logging - use INFO level to see warnings
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Enable CORS for frontend access
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Docker client
client = docker.from_env()

# In-memory store for running containers and servers
RUNNING_CONTAINERS = {}
MULLVAD_SERVERS = {}


def refresh_server_cache():
    """
    Refresh the Mullvad servers cache by fetching fresh data.
    Returns True if successful, False otherwise.
    """
    global MULLVAD_SERVERS
    logger.info("Refreshing server cache...")
    new_servers = get_mullvad_servers()
    if new_servers:
        MULLVAD_SERVERS = new_servers
        logger.info(f"Server cache refreshed successfully. {len(MULLVAD_SERVERS)} servers cached.")
        return True
    else:
        logger.warning("Failed to refresh server cache. Keeping existing cache.")
        return False


def _get_or_create_network(network_name):
    """
    Get a Docker network by name, or return None if it doesn't exist.
    Tries exact match first, then partial match (for Docker Compose network names).
    Returns the network object or None.
    """
    try:
        # Try exact match first
        networks = client.networks.list(names=[network_name])
        if networks:
            return networks[0]
        
        # Try finding network by partial name (Docker Compose may prepend project name)
        # e.g., "geosnappro-network" might be "geosnappro-thefinal_geosnappro-network"
        all_networks = client.networks.list()
        for net in all_networks:
            # Check if network name ends with the requested name or contains it
            if net.name == network_name or net.name.endswith(f"_{network_name}") or network_name in net.name:
                logger.debug(f"Found network '{net.name}' matching '{network_name}'")
                return net
        
        return None
    except Exception as e:
        logger.warning(f"Error checking for network '{network_name}': {e}")
        return None


def _wait_for_proxy_ready(container_name: str, username: str, password: str, port: int, timeout: int = 60) -> bool:
    """
    Wait for the gluetun proxy service to become ready.
    Polls the proxy with a simple HTTP request until it responds successfully.
    
    Args:
        container_name: Name of the gluetun container
        username: Proxy username
        password: Proxy password
        port: Host port mapped to container's 8888 (for reference, but we use container name)
        timeout: Maximum time to wait in seconds (default: 60)
    
    Returns:
        True if proxy becomes ready, False if timeout is reached
    """
    logger.info(f"Waiting for proxy service to be ready (container: {container_name}, timeout: {timeout}s)")
    start_time = time.time()
    check_interval = 2  # Check every 2 seconds
    max_attempts = timeout // check_interval
    
    # Use container name and internal port (8888) since we're in the same Docker network
    # The container name is accessible from within the Docker network
    proxy_url_container = f"http://{username}:{password}@{container_name}:8888"
    
    for attempt in range(max_attempts):
        elapsed = time.time() - start_time
        try:
            # Try to make a simple HTTP request through the proxy
            # Use a well-known endpoint that should work through proxy
            # Use container name instead of localhost since we're in Docker network
            response = requests.get(
                "http://httpbin.org/ip",
                proxies={"http": proxy_url_container, "https": proxy_url_container},
                timeout=5
            )
            if response.status_code == 200:
                logger.info(f"Proxy service is ready after {elapsed:.1f}s (attempt {attempt + 1})")
                return True
        except requests.exceptions.ProxyError as e:
            # Proxy not ready yet, continue waiting
            if attempt % 5 == 0:  # Log every 5th attempt to reduce noise
                logger.debug(f"Proxy check attempt {attempt + 1}: ProxyError - {str(e)[:100]}")
        except requests.exceptions.Timeout:
            # Request timed out, proxy might not be ready
            if attempt % 5 == 0:
                logger.debug(f"Proxy check attempt {attempt + 1}: Timeout")
        except requests.exceptions.ConnectionError as e:
            # Connection error - proxy not ready or container not accessible
            if attempt % 5 == 0:
                logger.debug(f"Proxy check attempt {attempt + 1}: ConnectionError - {str(e)[:100]}")
        except Exception as e:
            # Other errors, log but continue
            if attempt % 5 == 0:
                logger.debug(f"Proxy check attempt {attempt + 1} failed: {type(e).__name__} - {str(e)[:100]}")
        
        if attempt < max_attempts - 1:
            time.sleep(check_interval)
    
    elapsed = time.time() - start_time
    logger.warning(f"Proxy service did not become ready after {elapsed:.1f}s (container: {container_name})")
    # Try to get container logs for debugging
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=20).decode('utf-8', errors='ignore')
        logger.warning(f"Last 20 lines of container logs:\n{logs}")
    except Exception as log_error:
        logger.debug(f"Could not retrieve container logs: {log_error}")
    return False


def cleanup_orphaned_containers():
    """
    Removes any Gluetun containers that were created by this API but are no longer tracked.
    """
    logger.info("Cleaning up orphaned containers...")
    # Get all tracked container IDs (Docker container IDs, not UUIDs)
    tracked_container_ids = {info["container_id"] for info in RUNNING_CONTAINERS.values()}
    
    for container in client.containers.list(all=True):
        if container.name.startswith("gluetun-"):
            if container.id not in tracked_container_ids:
                logger.info(f"Removing orphaned container: {container.name}")
                try:
                    container.stop()
                    container.remove()
                except Exception as e:
                    logger.warning(f"Error removing orphaned container {container.name}: {e}")


def get_mullvad_servers():
    """
    Starts a temporary Gluetun container to get the list of Mullvad servers.
    """
    logger.info("Fetching Mullvad servers...")
    container_name = f"gluetun-server-list-{uuid.uuid4()}"
    container = None
    try:
        # Use the actual Wireguard credentials for server listing
        container = client.containers.run(
            "qmcgaw/gluetun",
            name=container_name,
            cap_add=["NET_ADMIN"],
            devices=["/dev/net/tun:/dev/net/tun"],  # REQUIRED: TUN device for VPN
            dns=["8.8.8.8", "1.1.1.1"],  # Configure DNS servers for initial resolution
            environment={
                "VPN_SERVICE_PROVIDER": "mullvad",
                "VPN_TYPE": "wireguard",
                "WIREGUARD_PRIVATE_KEY": config.WIREGUARD_PRIVATE_KEY,
                "WIREGUARD_ADDRESSES": config.WIREGUARD_ADDRESSES,
                "MULLVAD_COUNTRY": "us",
                # Health check configuration - make checks more tolerant during server list fetch
                "HEALTH_VPN_DURATION_INITIAL": "60s",
                "HEALTH_VPN_DURATION_ADDITION": "10s",
                "HEALTH_SUCCESS_WAIT_DURATION": "10s",
                "HEALTH_TARGET_ADDRESS": "1.1.1.1:443",
            },
            detach=True,
        )

        # Wait for the container to be ready - just wait for server list to be available
        # We don't need full VPN connection, just need the gluetun binary to be ready
        timeout = 60  # 60 second timeout
        start_time = time.time()
        last_logs = []
        ready = False
        
        # Wait a bit for container to start
        time.sleep(2)
        
        # Poll container status and logs
        try:
            for _ in range(20):  # Check 20 times
                if time.time() - start_time > timeout:
                    logger.error("Timeout waiting for container to be ready")
                    break
                    
                container.reload()
                if container.status != "running":
                    logger.warning(f"Container exited while waiting (status: {container.status})")
                    # Try to get logs even if container exited
                    try:
                        logs = container.logs().decode("utf-8")
                        last_logs = logs.split("\n")[-10:]
                        logger.warning(f"Last log lines: {''.join(last_logs)}")
                    except:
                        pass
                    break
                
                # Check if servers.json has been created (indicates gluetun is ready)
                try:
                    logs = container.logs().decode("utf-8")
                    if "servers.json" in logs or "creating" in logs.lower():
                        ready = True
                        logger.info("Container appears ready")
                        break
                except:
                    pass
                
                time.sleep(1)
        except Exception as e:
            logger.error(f"Error checking container status: {e}")

        # Reload container to get current status
        container.reload()
        
        # Check if container is still running
        if container.status != "running":
            logger.error(f"Container is not running (status: {container.status})")
            if last_logs:
                logger.error(f"Container logs before exit:\n{''.join(last_logs)}")
            return {}

        # Get the server list - try reading the servers.json file directly
        # The file is created at /gluetun/servers.json
        try:
            exec_result = container.exec_run("cat /gluetun/servers.json")
            if exec_result.exit_code == 0:
                servers_json = exec_result.output.decode("utf-8")
            else:
                # Fallback: try the gluetun command with proper path
                exec_result = container.exec_run("sh -c '/gluetun-entrypoint' 'gluetun' 'servers' 'list' 'mullvad' 'wireguard'")
                if exec_result.exit_code != 0:
                    logger.error(f"Error getting server list: {exec_result.output.decode('utf-8')}")
                    return {}
                servers_json = exec_result.output.decode("utf-8")
        except Exception as e:
            logger.error(f"Exception getting server list: {e}")
            return {}
        servers = json.loads(servers_json)
        
        # Debug: Log the structure to understand what we're working with
        logger.debug(f"Servers JSON top-level keys: {list(servers.keys())[:10] if isinstance(servers, dict) else 'not a dict'}")
        
        # Create a user-friendly mapping
        server_map = {}
        
        # The servers.json structure has providers as top-level keys
        # e.g., {"version": "...", "mullvad": {"version": 1, "timestamp": ..., "servers": [...]}, ...}
        if isinstance(servers, dict) and "mullvad" in servers:
            mullvad_data = servers.get("mullvad", {})
            logger.debug(f"Mullvad data keys: {list(mullvad_data.keys())[:10] if isinstance(mullvad_data, dict) else 'not a dict'}")
            
            # The structure is: mullvad -> servers (flat list of server objects)
            if "servers" in mullvad_data:
                servers_list = mullvad_data.get("servers", [])
                logger.debug(f"Found {len(servers_list)} servers in mullvad.servers list")
                
                # Filter for wireguard servers and create mapping
                for server in servers_list:
                    if isinstance(server, dict):
                        # Check if it's a wireguard server (vpn field should be "wireguard" or check for wireguard-specific fields)
                        vpn_type = server.get("vpn", "").lower()
                        hostname = server.get("hostname", "")
                        
                        # Include wireguard servers (or all servers if vpn field is not present)
                        if vpn_type == "wireguard" or (not vpn_type and "wgpubkey" in server) or "wireguard" in str(server).lower():
                            if hostname:
                                # Create a user-friendly key
                                country = server.get("country", "unknown")
                                city = server.get("city", "unknown")
                                server_key = f"{country}-{city}-{hostname}"
                                
                                # Normalize the key (remove spaces, make consistent)
                                server_key = server_key.replace(" ", "-").lower()
                                server_map[server_key] = server
                                
                logger.debug(f"Created {len(server_map)} server mappings from {len(servers_list)} total servers")
            else:
                logger.warning("No 'servers' key found in mullvad data")
        else:
            logger.warning(f"No 'mullvad' key found in servers JSON. Available keys: {list(servers.keys())[:20] if isinstance(servers, dict) else 'not a dict'}")

        logger.info(f"Fetched {len(server_map)} Mullvad servers.")
        if len(server_map) == 0:
            logger.warning("Server map is empty. This may indicate a parsing issue or empty server list.")
            # Log a sample of the actual structure for debugging
            if isinstance(servers, dict):
                logger.warning(f"Sample of servers.json structure (first 500 chars): {json.dumps(servers, indent=2)[:500]}")
        return server_map

    except (docker.errors.ContainerError, docker.errors.APIError, Exception) as e:
        logger.error(f"Error getting Mullvad servers: {e}")
        return {}
    finally:
        if container:
            try:
                container.reload()
                if container.status == "running":
                    container.stop()
                container.remove()
                logger.info(f"Stopped and removed temporary container: {container_name}")
            except docker.errors.NotFound:
                pass  # Container was already removed
            except Exception as e:
                logger.error(f"Error cleaning up container: {e}")


# Flag to track if initial setup has been run
_initialized = False

@app.before_request
def initial_setup():
    global _initialized, MULLVAD_SERVERS
    if not _initialized:
        cleanup_orphaned_containers()
        MULLVAD_SERVERS = get_mullvad_servers()
        _initialized = True


@app.route("/servers", methods=["GET"])
def get_servers():
    """
    Get list of Mullvad servers.
    
    Query parameters:
    - country: Filter servers by country (case-insensitive, partial match)
    - city: Filter servers by city (case-insensitive, partial match)
    - force: Force refresh the server cache (true/1/yes) before returning results
    
    Examples:
    - GET /servers?country=United States
    - GET /servers?city=New York
    - GET /servers?country=United States&city=New York
    - GET /servers?force=true
    """
    # Check if force refresh is requested
    force_refresh = request.args.get("force", "").lower() in ("true", "1", "yes")
    if force_refresh:
        refresh_server_cache()
    
    filtered_servers = MULLVAD_SERVERS.copy()
    
    # Get query parameters
    country_filter = request.args.get("country", "").strip().lower()
    city_filter = request.args.get("city", "").strip().lower()
    
    # Apply filters if provided
    if country_filter or city_filter:
        filtered_servers = {}
        for server_key, server_data in MULLVAD_SERVERS.items():
            # Check country filter - match complete words or partial match
            country_match = True
            if country_filter:
                server_country = server_data.get("country", "").lower()
                # Try exact match first, then partial match
                # Split filter into words for better matching
                filter_words = country_filter.split()
                country_match = (
                    country_filter == server_country or  # Exact match
                    country_filter in server_country or  # Filter is substring of country
                    server_country.startswith(country_filter) or  # Country starts with filter
                    all(word in server_country for word in filter_words)  # All words present
                )
            
            # Check city filter - match complete words or partial match
            city_match = True
            if city_filter:
                server_city = server_data.get("city", "").lower()
                filter_words = city_filter.split()
                city_match = (
                    city_filter == server_city or  # Exact match
                    city_filter in server_city or  # Filter is substring of city
                    server_city.startswith(city_filter) or  # City starts with filter
                    all(word in server_city for word in filter_words)  # All words present
                )
            
            # Include server if both filters match (or if filter not provided)
            if country_match and city_match:
                filtered_servers[server_key] = server_data
        
        logger.debug(f"Filtered servers: country='{country_filter}', city='{city_filter}', "
                    f"result: {len(filtered_servers)} servers")
    
    return jsonify(filtered_servers)


@app.route("/locations", methods=["GET"])
def get_locations():
    """
    Get a friendly list of all locations organized by country and city.
    
    Query parameters:
    - force: Force refresh the server cache (true/1/yes) before returning results
    
    Returns a hierarchical structure:
    {
      "countries": [
        {
          "name": "United States",
          "cities": [
            {
              "name": "New York",
              "server_count": 5,
              "sample_hostname": "us-nyc-wg-301"
            }
          ]
        }
      ]
    }
    
    This endpoint is designed for frontend use to display location selection options.
    """
    # Check if force refresh is requested
    force_refresh = request.args.get("force", "").lower() in ("true", "1", "yes")
    if force_refresh:
        refresh_server_cache()
    
    locations = {}
    
    # Organize servers by country and city
    for server_key, server_data in MULLVAD_SERVERS.items():
        country = server_data.get("country", "Unknown")
        city = server_data.get("city", "Unknown")
        hostname = server_data.get("hostname", "")
        
        # Initialize country if not exists
        if country not in locations:
            locations[country] = {}
        
        # Initialize city if not exists
        if city not in locations[country]:
            locations[country][city] = {
                "servers": [],
                "count": 0
            }
        
        # Add server hostname to the city's server list
        if hostname:
            locations[country][city]["servers"].append(hostname)
            locations[country][city]["count"] += 1
    
    # Convert to frontend-friendly format
    countries_list = []
    for country_name in sorted(locations.keys()):
        cities_list = []
        for city_name in sorted(locations[country_name].keys()):
            city_data = locations[country_name][city_name]
            cities_list.append({
                "name": city_name,
                "server_count": city_data["count"],
                "sample_hostname": city_data["servers"][0] if city_data["servers"] else None
            })
        
        countries_list.append({
            "name": country_name,
            "city_count": len(cities_list),
            "total_servers": sum(city["server_count"] for city in cities_list),
            "cities": cities_list
        })
    
    return jsonify({
        "countries": countries_list,
        "total_countries": len(countries_list),
        "total_cities": sum(country["city_count"] for country in countries_list),
        "total_servers": sum(country["total_servers"] for country in countries_list)
    })


@app.route("/start", methods=["POST"])
def start_gluetun():
    """
    Start a Gluetun VPN container.
    
    Request body (JSON):
    - server: Server key (e.g., "usa-new-york-ny-us-nyc-wg-301") [required if country/city not provided]
    - country: Country name to search for (case-insensitive, partial match) [optional]
    - city: City name to search for (case-insensitive, partial match) [optional]
    
    If country/city are provided, the first matching server will be selected.
    If server is provided, it takes precedence over country/city.
    
    Examples:
    - {"server": "usa-new-york-ny-us-nyc-wg-301"}
    - {"country": "USA", "city": "New York"}
    - {"country": "Canada"}
    """
    if len(RUNNING_CONTAINERS) >= config.INSTANCE_LIMIT:
        return jsonify({"error": "Instance limit reached"}), 429

    data = request.get_json()
    server_name = data.get("server")
    country_filter = data.get("country", "").strip().lower()
    city_filter = data.get("city", "").strip().lower()
    
    # If server name is provided, use it directly
    if server_name:
        if server_name not in MULLVAD_SERVERS:
            return jsonify({"error": "Invalid server"}), 400
    # Otherwise, try to find a server by country/city
    elif country_filter or city_filter:
        # Filter servers by country/city
        matching_servers = []
        for key, server_data in MULLVAD_SERVERS.items():
            country_match = True
            if country_filter:
                server_country = server_data.get("country", "").lower()
                filter_words = country_filter.split()
                country_match = (
                    country_filter == server_country or
                    country_filter in server_country or
                    server_country.startswith(country_filter) or
                    all(word in server_country for word in filter_words)
                )
            
            city_match = True
            if city_filter:
                server_city = server_data.get("city", "").lower()
                filter_words = city_filter.split()
                city_match = (
                    city_filter == server_city or
                    city_filter in server_city or
                    server_city.startswith(city_filter) or
                    all(word in server_city for word in filter_words)
                )
            
            if country_match and city_match:
                matching_servers.append(key)
        
        if not matching_servers:
            error_msg = "No server found"
            if country_filter and city_filter:
                error_msg += f" for country '{country_filter}' and city '{city_filter}'"
            elif country_filter:
                error_msg += f" for country '{country_filter}'"
            elif city_filter:
                error_msg += f" for city '{city_filter}'"
            return jsonify({"error": error_msg}), 400
        
        # Use the first matching server (you could also randomize this)
        server_name = matching_servers[0]
        logger.info(f"Selected server '{server_name}' from {len(matching_servers)} matching servers "
                   f"(country: {country_filter or 'any'}, city: {city_filter or 'any'})")
    else:
        return jsonify({"error": "Must provide either 'server' or 'country'/'city' parameters"}), 400

    username = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    password = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    container_id = str(uuid.uuid4())
    container_name = f"gluetun-{container_id}"
    
    # Get network name from environment or use default
    network_name = os.getenv("DOCKER_NETWORK", "bridge")
    
    # Validate network exists, fallback to bridge if not found
    network_to_use = None
    network_obj = None
    if network_name != "bridge":
        network_obj = _get_or_create_network(network_name)
        if network_obj:
            # Use the actual network name (might be different due to Docker Compose naming)
            network_to_use = network_obj.name
            logger.debug(f"Using network: {network_to_use} (requested: {network_name})")
        else:
            logger.warning(f"Network '{network_name}' not found, falling back to 'bridge'")
            network_to_use = "bridge"
    else:
        network_to_use = "bridge"

    try:
        # Create container configuration
        container_config = {
            "image": "qmcgaw/gluetun",
            "name": container_name,
            "cap_add": ["NET_ADMIN"],
            "devices": ["/dev/net/tun:/dev/net/tun"],  # REQUIRED: TUN device for VPN
            "dns": ["8.8.8.8", "1.1.1.1"],  # Configure DNS servers for initial resolution
            "ports": {"8888/tcp": None},  # Let Docker assign a random port
            "environment": {
                "VPN_SERVICE_PROVIDER": "mullvad",
                "VPN_TYPE": "wireguard",
                "WIREGUARD_PRIVATE_KEY": config.WIREGUARD_PRIVATE_KEY,
                "WIREGUARD_ADDRESSES": config.WIREGUARD_ADDRESSES,
                # Use SERVER_HOSTNAMES (comma-separated list) instead of MULLVAD_SERVER_HOSTNAME
                "SERVER_HOSTNAMES": MULLVAD_SERVERS[server_name]["hostname"],
                # HTTP proxy configuration (correct variable names per gluetun docs)
                "HTTPPROXY": "on",
                "HTTPPROXY_USER": username,
                "HTTPPROXY_PASSWORD": password,
                "HTTPPROXY_LISTENING_ADDRESS": ":8888",  # Default, but explicit
                "HTTPPROXY_LOG": "off",  # Disable verbose logging
                "HTTPPROXY_STEALTH": "off",  # Include proxy headers
                # Health check configuration - make checks more tolerant of slow connections
                "HEALTH_VPN_DURATION_INITIAL": "60s",  # Give VPN 60s to establish on first check (default: 6s)
                "HEALTH_VPN_DURATION_ADDITION": "10s",  # Allow 10s for ongoing health checks (default: 5s)
                "HEALTH_SUCCESS_WAIT_DURATION": "10s",  # Wait 10s between successful health checks (default: 5s)
                "HEALTH_TARGET_ADDRESS": "1.1.1.1:443",  # Use Cloudflare's reliable DNS over TLS endpoint
            },
            "detach": True,
        }
        
        # Create container without network first (will use bridge by default)
        # This avoids Docker-in-Docker network attachment issues
        container = client.containers.create(**container_config)
        
        # Connect to network if not using bridge (must be done before starting)
        if network_to_use != "bridge" and network_obj:
            try:
                # Disconnect from default bridge network first to avoid conflicts
                try:
                    default_bridge = client.networks.get("bridge")
                    default_bridge.disconnect(container.id, force=True)
                    logger.debug(f"Disconnected container {container_name} from bridge network")
                except Exception as bridge_error:
                    logger.debug(f"Could not disconnect from bridge (may not be connected): {bridge_error}")
                
                # Connect to the custom network
                network_obj.connect(container.id)
                logger.debug(f"Connected container {container_name} to network {network_to_use}")
            except Exception as network_error:
                logger.warning(f"Failed to connect container to network {network_to_use}: {network_error}")
                logger.info("Container will use bridge network instead")
        
        # Start the container
        container.start()
        
        # Wait a moment for container to start and ports to be assigned
        time.sleep(0.5)
        
        # Get the assigned port
        container.reload()
        assigned_port = container.ports["8888/tcp"][0]["HostPort"]
        
        # Wait for the proxy service to be ready
        # The gluetun container needs time to establish VPN connection and start proxy
        proxy_ready = _wait_for_proxy_ready(container_name, username, password, assigned_port, timeout=60)
        if not proxy_ready:
            # Clean up the container if proxy didn't become ready
            try:
                container.stop()
                container.remove()
            except Exception as cleanup_error:
                logger.warning(f"Error cleaning up container after proxy readiness timeout: {cleanup_error}")
            return jsonify({"error": "Proxy service did not become ready within timeout period"}), 504

        RUNNING_CONTAINERS[container_id] = {
            "container_id": container.id,
            "container_name": container_name,
            "server": server_name,
            "username": username,
            "password": password,
            "port": assigned_port,
        }

        return jsonify(
            {
                "id": container_id,
                "proxy": f"http://{username}:{password}@localhost:{assigned_port}",
            }
        )

    except docker.errors.NotFound as e:
        error_msg = str(e)
        if "network" in error_msg.lower():
            logger.error(f"Network error starting Gluetun container: {e}")
            return jsonify({"error": f"Network configuration error: {error_msg}"}), 500
        else:
            logger.error(f"Container not found error: {e}")
            return jsonify({"error": "Failed to start Gluetun container"}), 500
    except docker.errors.ContainerError as e:
        logger.error(f"Error starting Gluetun container: {e}")
        return jsonify({"error": "Failed to start Gluetun container"}), 500
    except docker.errors.APIError as e:
        logger.error(f"Docker API error starting Gluetun container: {e}")
        return jsonify({"error": f"Docker API error: {str(e)}"}), 500
    except Exception as e:
        logger.exception(f"Unexpected error starting Gluetun container: {e}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route("/stop", methods=["POST"])
def stop_gluetun():
    data = request.get_json()
    container_id = data.get("id")
    if container_id not in RUNNING_CONTAINERS:
        return jsonify({"error": "Container not found"}), 404

    container_info = RUNNING_CONTAINERS[container_id]
    try:
        container = client.containers.get(container_info["container_id"])
        container.stop()
        return jsonify({"message": "Container stopped"})
    except docker.errors.NotFound:
        return jsonify({"error": "Container not found"}), 404


@app.route("/destroy", methods=["POST"])
def destroy_gluetun():
    data = request.get_json()
    container_id = data.get("id")
    if container_id not in RUNNING_CONTAINERS:
        return jsonify({"error": "Container not found"}), 404

    container_info = RUNNING_CONTAINERS.pop(container_id)
    try:
        container = client.containers.get(container_info["container_id"])
        container.stop()
        container.remove()
        logger.info(f"Destroyed gluetun proxy container: {container_id}")
        return jsonify({"message": "Container destroyed"})
    except docker.errors.NotFound:
        # Container already removed, but we've already popped it from RUNNING_CONTAINERS
        logger.warning(f"Container {container_id} not found in Docker (may have been already removed)")
        return jsonify({"message": "Container destroyed (was already removed)"})
    except Exception as e:
        logger.error(f"Error destroying container {container_id}: {e}")
        # Even if there's an error, we've already removed it from RUNNING_CONTAINERS
        # so it won't count against the limit
        return jsonify({"error": f"Error destroying container: {str(e)}"}), 500


@app.route("/status", methods=["GET"])
def get_status():
    return jsonify(RUNNING_CONTAINERS)


@app.route("/servers/refresh", methods=["POST"])
def refresh_servers():
    """
    Explicitly refresh the server cache.
    
    This endpoint forces a refresh of the Mullvad server list by starting
    a temporary Gluetun container and fetching the latest server data.
    
    Response:
    - Success (200): {"message": "Server cache refreshed", "server_count": 123}
    - Error (500): {"error": "Failed to refresh server cache"}
    """
    success = refresh_server_cache()
    if success:
        return jsonify({
            "message": "Server cache refreshed",
            "server_count": len(MULLVAD_SERVERS)
        })
    else:
        return jsonify({"error": "Failed to refresh server cache"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
