"""
Gluetun Kubernetes API Server

Flask-based API server for managing Gluetun VPN containers in Kubernetes.
This is a Kubernetes-native implementation that provisions Gluetun pods
instead of Docker containers.
"""

import ast
import json
import logging
import os
import random
import time
import uuid
from typing import Dict, Tuple

from flask import Flask, jsonify, request
from flask_cors import CORS
from kubernetes import client
from kubernetes.stream import stream

import config
from k8s_manager import GluetunK8sManager

# Configure logging
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

# Initialize Kubernetes manager
k8s_manager = GluetunK8sManager(
    namespace=config.K8S_NAMESPACE,
    firewall_input_ports=config.FIREWALL_INPUT_PORTS,
)

# In-memory store for running pods and servers
RUNNING_PODS = {}
MULLVAD_SERVERS = {}


def _parse_servers_dict(servers: Dict) -> Dict:
    """Convert the raw servers dictionary into the API's expected mapping."""
    server_map = {}

    if isinstance(servers, dict) and "mullvad" in servers:
        mullvad_data = servers.get("mullvad", {})

        if "servers" in mullvad_data:
            servers_list = mullvad_data.get("servers", [])
            logger.debug(f"Found {len(servers_list)} servers in mullvad.servers list")

            for server in servers_list:
                if isinstance(server, dict):
                    vpn_type = server.get("vpn", "").lower()
                    hostname = server.get("hostname", "")

                    if vpn_type == "wireguard" or (not vpn_type and "wgpubkey" in server):
                        if hostname:
                            country = server.get("country", "unknown")
                            city = server.get("city", "unknown")
                            server_key = f"{country}-{city}-{hostname}"
                            server_key = server_key.replace(" ", "-").lower()
                            server_map[server_key] = server
        else:
            logger.warning("No 'servers' key found in mullvad data")
    else:
        available = list(servers.keys())[:20] if isinstance(servers, dict) else "not a dict"
        logger.warning(f"No 'mullvad' key found in servers JSON. Available keys: {available}")

    if not server_map:
        logger.warning("Server map is empty after parsing Mullvad servers payload.")
        if isinstance(servers, dict):
            logger.warning(f"Sample of servers payload (first 500 chars): {json.dumps(servers, indent=2)[:500]}")

    return server_map


def _load_servers_from_payload(payload: str, source: str) -> Dict:
    """Parse a raw JSON payload and build the server map."""
    if not payload:
        raise ValueError(f"No server data received from {source}")

    try:
        servers = json.loads(payload)
    except json.JSONDecodeError:
        try:
            servers = ast.literal_eval(payload)
            logger.debug(f"Parsed server list using literal_eval fallback for {source}.")
        except (ValueError, SyntaxError) as parse_error:
            raise ValueError(f"Failed to parse server list from {source}: {parse_error}") from parse_error

    return _parse_servers_dict(servers)


def _load_preconfigured_servers() -> Tuple[Dict, bool]:
    """
    Load Mullvad servers from pre-configured sources (environment variable or file).

    Returns:
        Tuple of (server_map, attempted). server_map will be empty dict if load failed.
    """
    attempted = False

    if config.SERVERS_JSON:
        attempted = True
        logger.info("Loading Mullvad servers from SERVERS_JSON environment variable...")
        try:
            server_map = _load_servers_from_payload(config.SERVERS_JSON, "SERVERS_JSON environment variable")
            if server_map:
                logger.info(f"Loaded {len(server_map)} Mullvad servers from SERVERS_JSON environment variable.")
                return server_map, attempted
            logger.warning("SERVERS_JSON environment variable provided but resulted in an empty server map.")
        except ValueError as error:
            logger.error(str(error))

    attempted_paths = set()

    if config.SERVERS_FILE_PATH:
        attempted = True
        file_path = os.path.expanduser(config.SERVERS_FILE_PATH)
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        attempted_paths.add(file_path)

        if not os.path.exists(file_path):
            logger.error(f"SERVERS_FILE_PATH is set to '{file_path}' but the file does not exist.")
        else:
            logger.info(f"Loading Mullvad servers from file: {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    payload = file.read()
                server_map = _load_servers_from_payload(payload, f"file '{file_path}'")
                if server_map:
                    logger.info(f"Loaded {len(server_map)} Mullvad servers from file '{file_path}'.")
                    return server_map, attempted
                logger.warning(f"File '{file_path}' was read but resulted in an empty server map.")
            except OSError as error:
                logger.error(f"Failed to read SERVERS_FILE_PATH '{file_path}': {error}")
            except ValueError as error:
                logger.error(str(error))

    default_path = os.path.expanduser(config.DEFAULT_SERVERS_FILE_PATH or "")
    if default_path and default_path not in attempted_paths:
        if not os.path.isabs(default_path):
            default_path = os.path.abspath(default_path)
        if os.path.exists(default_path):
            attempted = True
            logger.info(f"Loading Mullvad servers from bundled file: {default_path}")
            try:
                with open(default_path, "r", encoding="utf-8") as file:
                    payload = file.read()
                server_map = _load_servers_from_payload(payload, f"bundled file '{default_path}'")
                if server_map:
                    logger.info(f"Loaded {len(server_map)} Mullvad servers from bundled file '{default_path}'.")
                    return server_map, attempted
                logger.warning(f"Bundled file '{default_path}' read but resulted in an empty server map.")
            except OSError as error:
                logger.error(f"Failed to read bundled servers file '{default_path}': {error}")
            except ValueError as error:
                logger.error(str(error))
        else:
            logger.debug(f"Bundled servers file '{default_path}' not found; skipping.")

    return {}, attempted


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


def get_mullvad_servers() -> Dict:
    """
    Starts a temporary Gluetun pod to get the list of Mullvad servers.
    Uses Kubernetes Jobs for this purpose.
    """
    preconfigured_servers, attempted_preload = _load_preconfigured_servers()
    if preconfigured_servers:
        return preconfigured_servers
    if attempted_preload:
        logger.warning("Preconfigured Mullvad server data failed to load; falling back to Kubernetes job.")

    logger.info("Fetching Mullvad servers using Kubernetes Job...")
    job_name = f"gluetun-server-list-{uuid.uuid4()}"
    
    try:
        # Create a Kubernetes Job to fetch server list
        job_manifest = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": k8s_manager.namespace,
            },
            "spec": {
                "ttlSecondsAfterFinished": 30,  # Auto-cleanup after 30 seconds
                "template": {
                    "spec": {
                        "initContainers": [
                            {
                                "name": "gluetun-init",
                                "image": "qmcgaw/gluetun:latest",
                                "securityContext": {
                                    "capabilities": {
                                        "add": ["NET_ADMIN"]
                                    },
                                },
                                "env": [
                                    {"name": "VPN_SERVICE_PROVIDER", "value": "mullvad"},
                                    {"name": "VPN_TYPE", "value": "wireguard"},
                                    {"name": "WIREGUARD_PRIVATE_KEY", "value": config.WIREGUARD_PRIVATE_KEY},
                                    {"name": "WIREGUARD_ADDRESSES", "value": config.WIREGUARD_ADDRESSES},
                                ],
                                "command": [
                                    "sh",
                                    "-c",
                                    # Start Gluetun in background, wait for servers.json, then exit
                                    "/gluetun-entrypoint & GLUETUN_PID=$!; "
                                    "for i in $(seq 1 30); do "
                                    "if [ -f /gluetun/servers.json ]; then "
                                    "echo 'servers.json found!'; "
                                    "cat /gluetun/servers.json > /shared/servers.json; "
                                    "kill $GLUETUN_PID 2>/dev/null || true; "
                                    "exit 0; "
                                    "fi; "
                                    "echo 'Waiting for servers.json...'; "
                                    "sleep 2; "
                                    "done; "
                                    "echo 'Timeout waiting for servers.json'; "
                                    "kill $GLUETUN_PID 2>/dev/null || true; "
                                    "exit 1"
                                ],
                                "volumeMounts": [
                                    {
                                        "name": "shared-data",
                                        "mountPath": "/shared"
                                    }
                                ],
                            }
                        ],
                        "containers": [
                            {
                                "name": "reader",
                                "image": "busybox:latest",
                                "command": ["sh", "-c", "cat /shared/servers.json && sleep 5"],
                                "volumeMounts": [
                                    {
                                        "name": "shared-data",
                                        "mountPath": "/shared"
                                    }
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "shared-data",
                                "emptyDir": {}
                            }
                        ],
                        "restartPolicy": "Never",
                    }
                },
            },
        }
        
        # Create the job
        batch_api = client.BatchV1Api()
        job = batch_api.create_namespaced_job(
            namespace=k8s_manager.namespace,
            body=job_manifest
        )
        logger.info(f"Created server list job: {job_name}")
        
        # Wait for job to complete (longer timeout for init container)
        timeout = 90  # Increased timeout for Gluetun to start and fetch servers
        start_time = time.time()
        job_completed = False
        
        while time.time() - start_time < timeout:
            try:
                job_status = batch_api.read_namespaced_job_status(
                    name=job_name,
                    namespace=k8s_manager.namespace
                )
                
                if job_status.status.succeeded and job_status.status.succeeded > 0:
                    job_completed = True
                    break
                
                if job_status.status.failed and job_status.status.failed > 0:
                    logger.error("Job failed to complete")
                    break
                    
            except Exception as e:
                logger.warning(f"Error checking job status: {e}")
            
            time.sleep(2)
        
        if not job_completed:
            logger.error("Job did not complete successfully within timeout")
            # Cleanup job
            try:
                batch_api.delete_namespaced_job(
                    name=job_name,
                    namespace=k8s_manager.namespace,
                    propagation_policy='Background'
                )
            except:
                pass
            return {}
        
        # Get pod logs to extract server list
        # Find the pod created by the job
        core_api = client.CoreV1Api()
        pods = core_api.list_namespaced_pod(
            namespace=k8s_manager.namespace,
            label_selector=f"job-name={job_name}"
        )
        
        if not pods.items:
            logger.error("No pods found for server list job")
            return {}
        
        # Pick the newest pod for this job (in case multiple exist briefly)
        pods.items.sort(key=lambda pod: pod.metadata.creation_timestamp, reverse=True)
        pod_name = pods.items[0].metadata.name
        
        servers_payload = ""
        try:
            servers_payload = stream(
                core_api.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=k8s_manager.namespace,
                container="reader",
                command=["cat", "/shared/servers.json"],
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            ).strip()
        except Exception as exec_error:
            logger.warning(
                f"Exec to read servers.json from reader container failed (pod: {pod_name}). "
                f"Falling back to pod logs. Error: {exec_error}"
            )
        
        if not servers_payload:
            logs = ""
            last_error = None
            for attempt in range(15):
                try:
                    logs = core_api.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=k8s_manager.namespace,
                        container="reader",
                        timestamps=False,
                    ).strip()
                    if logs:
                        break
                except Exception as e:
                    last_error = e
                time.sleep(1)
            
            if not logs:
                if last_error:
                    logger.error(f"Failed to retrieve server list from reader container logs: {last_error}")
                else:
                    logger.error("Server list job completed but produced no output from reader container.")
                return {}
            
            servers_payload = logs
        
        try:
            server_map = _load_servers_from_payload(
                servers_payload,
                f"server list job pod '{pod_name}'"
            )
        except ValueError as error:
            logger.error(str(error))
            return {}
        
        logger.info(f"Fetched {len(server_map)} Mullvad servers.")
        
        # Cleanup job
        try:
            batch_api.delete_namespaced_job(
                name=job_name,
                namespace=k8s_manager.namespace,
                propagation_policy='Background'
            )
        except:
            pass
        
        return server_map
        
    except Exception as e:
        logger.error(f"Error getting Mullvad servers: {e}")
        return {}


def cleanup_orphaned_pods():
    """Clean up any orphaned or failed Gluetun pods."""
    logger.info("Cleaning up orphaned and failed pods...")
    cleaned = k8s_manager.cleanup_failed_pods()
    logger.info(f"Cleaned up {cleaned} pods")


# Flag to track if initial setup has been run
_initialized = False

@app.before_request
def initial_setup():
    global _initialized, MULLVAD_SERVERS
    if not _initialized:
        cleanup_orphaned_pods()
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
    """
    force_refresh = request.args.get("force", "").lower() in ("true", "1", "yes")
    if force_refresh:
        refresh_server_cache()
    
    filtered_servers = MULLVAD_SERVERS.copy()
    
    country_filter = request.args.get("country", "").strip().lower()
    city_filter = request.args.get("city", "").strip().lower()
    
    if country_filter or city_filter:
        filtered_servers = {}
        for server_key, server_data in MULLVAD_SERVERS.items():
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
                filtered_servers[server_key] = server_data
    
    return jsonify(filtered_servers)


@app.route("/locations", methods=["GET"])
def get_locations():
    """
    Get a friendly list of all locations organized by country and city.
    """
    force_refresh = request.args.get("force", "").lower() in ("true", "1", "yes")
    if force_refresh:
        refresh_server_cache()
    
    locations = {}
    
    for server_key, server_data in MULLVAD_SERVERS.items():
        country = server_data.get("country", "Unknown")
        city = server_data.get("city", "Unknown")
        hostname = server_data.get("hostname", "")
        
        if country not in locations:
            locations[country] = {}
        
        if city not in locations[country]:
            locations[country][city] = {
                "servers": [],
                "count": 0
            }
        
        if hostname:
            locations[country][city]["servers"].append(hostname)
            locations[country][city]["count"] += 1
    
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
    Start a Gluetun VPN pod in Kubernetes.
    
    Request body (JSON):
    - server: Server key (e.g., "usa-new-york-ny-us-nyc-wg-301") [required if country/city not provided]
    - country: Country name to search for (case-insensitive, partial match) [optional]
    - city: City name to search for (case-insensitive, partial match) [optional]
    """
    if len(RUNNING_PODS) >= config.INSTANCE_LIMIT:
        return jsonify({"error": "Instance limit reached"}), 429

    data = request.get_json()
    server_name = data.get("server")
    country_filter = data.get("country", "").strip().lower()
    city_filter = data.get("city", "").strip().lower()
    
    if server_name:
        if server_name not in MULLVAD_SERVERS:
            return jsonify({"error": "Invalid server"}), 400
    elif country_filter or city_filter:
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
        
        # Select a random server from the matching list
        server_name = random.choice(matching_servers)
        logger.info(f"Selected random server '{server_name}' from {len(matching_servers)} matching servers")
    else:
        return jsonify({"error": "Must provide either 'server' or 'country'/'city' parameters"}), 400

    try:
        # Create Gluetun pod in Kubernetes
        pod_info = k8s_manager.create_gluetun_pod(
            server_hostname=MULLVAD_SERVERS[server_name]["hostname"],
            wireguard_private_key=config.WIREGUARD_PRIVATE_KEY,
            wireguard_addresses=config.WIREGUARD_ADDRESSES,
            server_name=server_name,
        )
        
        # Store in running pods
        RUNNING_PODS[pod_info["id"]] = {
            "pod_name": pod_info["pod_name"],
            "pod_ip": pod_info["pod_ip"],
            "server": server_name,
            "username": pod_info["username"],
            "password": pod_info["password"],
            "port": pod_info["port"],
            "status": pod_info["status"],
            "service_name": pod_info.get("service_name"),
            "service_cluster_ip": pod_info.get("service_cluster_ip"),
            "service_dns": pod_info.get("service_dns"),
            "service_port": pod_info.get("service_port"),
            "service_url": pod_info.get("service_url"),
        }
        
        return jsonify({
            "id": pod_info["id"],
            "proxy": pod_info["proxy"],
            "pod_name": pod_info["pod_name"],
            "pod_ip": pod_info["pod_ip"],
            "username": pod_info["username"],
            "password": pod_info["password"],
            "service_name": pod_info.get("service_name"),
            "service_cluster_ip": pod_info.get("service_cluster_ip"),
            "service_dns": pod_info.get("service_dns"),
            "service_port": pod_info.get("service_port"),
            "service_url": pod_info.get("service_url"),
        })
        
    except Exception as e:
        logger.exception(f"Failed to start Gluetun pod: {e}")
        return jsonify({"error": f"Failed to start Gluetun pod: {str(e)}"}), 500


@app.route("/stop", methods=["POST"])
def stop_gluetun():
    """Stop is not applicable for Kubernetes pods - use destroy instead."""
    return jsonify({"error": "Stop is not supported for Kubernetes pods. Use /destroy instead."}), 400


@app.route("/destroy", methods=["POST"])
def destroy_gluetun():
    """
    Destroy a Gluetun VPN pod.
    
    Request body (JSON):
    - id: Pod ID (UUID)
    """
    data = request.get_json()
    pod_id = data.get("id")
    
    if pod_id not in RUNNING_PODS:
        return jsonify({"error": "Pod not found"}), 404
    
    try:
        success = k8s_manager.delete_gluetun_pod(pod_id)
        if success:
            RUNNING_PODS.pop(pod_id, None)
            return jsonify({"message": "Pod destroyed"})
        else:
            return jsonify({"error": "Failed to destroy pod"}), 500
    except Exception as e:
        logger.exception(f"Failed to destroy pod: {e}")
        return jsonify({"error": f"Failed to destroy pod: {str(e)}"}), 500


@app.route("/status", methods=["GET"])
def get_status():
    """Get status of all running Gluetun pods."""
    # Sync with actual Kubernetes state
    k8s_pods = k8s_manager.list_gluetun_pods()
    
    # Update our in-memory store
    for pod in k8s_pods:
        pod_id = pod["id"]
        RUNNING_PODS[pod_id] = {
            "pod_name": pod["pod_name"],
            "pod_ip": pod["pod_ip"],
            "server": pod["server"],
            "username": pod["username"],
            "password": pod["password"],
            "port": pod["port"],
            "status": pod["status"],
            "service_name": pod.get("service_name"),
            "service_cluster_ip": pod.get("service_cluster_ip"),
            "service_dns": pod.get("service_dns"),
            "service_port": pod.get("service_port"),
            "service_url": pod.get("service_url"),
        }
    
    # Remove pods that no longer exist in Kubernetes
    k8s_pod_ids = {pod["id"] for pod in k8s_pods}
    for pod_id in list(RUNNING_PODS.keys()):
        if pod_id not in k8s_pod_ids:
            RUNNING_PODS.pop(pod_id, None)
    
    return jsonify(RUNNING_PODS)


@app.route("/servers/refresh", methods=["POST"])
def refresh_servers():
    """
    Explicitly refresh the server cache.
    """
    success = refresh_server_cache()
    if success:
        return jsonify({
            "message": "Server cache refreshed",
            "server_count": len(MULLVAD_SERVERS)
        })
    else:
        return jsonify({"error": "Failed to refresh server cache"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Kubernetes readiness/liveness probes."""
    return jsonify({"status": "healthy", "servers_loaded": len(MULLVAD_SERVERS) > 0})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)

