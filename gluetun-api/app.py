import docker
import json
import logging
import os
import random
import string
import time
import uuid

from flask import Flask, jsonify, request

import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Docker client
client = docker.from_env()

# In-memory store for running containers and servers
RUNNING_CONTAINERS = {}
MULLVAD_SERVERS = {}


def cleanup_orphaned_containers():
    """
    Removes any Gluetun containers that were created by this API but are no longer tracked.
    """
    logger.info("Cleaning up orphaned containers...")
    for container in client.containers.list(all=True):
        if container.name.startswith("gluetun-"):
            if container.id not in RUNNING_CONTAINERS:
                logger.info(f"Removing orphaned container: {container.name}")
                container.stop()
                container.remove()


def get_mullvad_servers():
    """
    Starts a temporary Gluetun container to get the list of Mullvad servers.
    """
    logger.info("Fetching Mullvad servers...")
    container_name = f"gluetun-server-list-{uuid.uuid4()}"
    try:
        container = client.containers.run(
            "qmcgaw/gluetun",
            name=container_name,
            cap_add=["NET_ADMIN"],
            environment={
                "VPN_SERVICE_PROVIDER": "mullvad",
                "VPN_TYPE": "wireguard",
                "MULLVAD_COUNTRY": "us",
            },
            detach=True,
        )

        # Wait for the container to be ready by polling logs
        for line in container.logs(stream=True):
            if "Activating http proxy" in line.decode("utf-8"):
                break

        # Get the server list
        exec_result = container.exec_run("gluetun-entrypoint /gluetun-start /bin/gluetun servers list mullvad wireguard")
        if exec_result.exit_code != 0:
            logger.error(f"Error getting server list: {exec_result.output.decode('utf-8')}")
            return {}

        servers_json = exec_result.output.decode("utf-8")
        servers = json.loads(servers_json)

        # Create a user-friendly mapping
        server_map = {}
        for country, country_data in servers.get("countries", {}).items():
            for city, city_data in country_data.get("cities", []):
                for server in city_data.get("servers", []):
                    server_map[f"{country}-{city_data['name']}-{server['hostname']}"] = server

        logger.info(f"Fetched {len(server_map)} Mullvad servers.")
        return server_map

    except docker.errors.ContainerError as e:
        logger.error(f"Error getting Mullvad servers: {e}")
        return {}
    finally:
        try:
            container = client.containers.get(container_name)
            container.stop()
            container.remove()
            logger.info(f"Stopped and removed temporary container: {container_name}")
        except docker.errors.NotFound:
            pass  # Container was already removed


@app.before_first_request
def initial_setup():
    global MULLVAD_SERVERS
    cleanup_orphaned_containers()
    MULLVAD_SERVERS = get_mullvad_servers()


@app.route("/servers", methods=["GET"])
def get_servers():
    return jsonify(MULLVAD_SERVERS)


@app.route("/start", methods=["POST"])
def start_gluetun():
    if len(RUNNING_CONTAINERS) >= config.INSTANCE_LIMIT:
        return jsonify({"error": "Instance limit reached"}), 429

    data = request.get_json()
    server_name = data.get("server")
    if not server_name or server_name not in MULLVAD_SERVERS:
        return jsonify({"error": "Invalid server"}), 400

    username = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    password = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    container_id = str(uuid.uuid4())
    container_name = f"gluetun-{container_id}"

    try:
        container = client.containers.run(
            "qmcgaw/gluetun",
            name=container_name,
            cap_add=["NET_ADMIN"],
            environment={
                "VPN_SERVICE_PROVIDER": "mullvad",
                "VPN_TYPE": "wireguard",
                "WIREGUARD_PRIVATE_KEY": config.WIREGUARD_PRIVATE_KEY,
                "WIREGUARD_ADDRESSES": config.WIREGUARD_ADDRESSES,
                "MULLVAD_SERVER_HOSTNAME": MULLVAD_SERVERS[server_name]["hostname"],
                "HTTP_PROXY": "on",
                "HTTP_PROXY_USER": username,
                "HTTP_PROXY_PASSWORD": password,
            },
            ports={"8888/tcp": None},  # Let Docker assign a random port
            detach=True,
        )

        # Get the assigned port
        container.reload()
        assigned_port = container.ports["8888/tcp"][0]["HostPort"]

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

    except docker.errors.ContainerError as e:
        logger.error(f"Error starting Gluetun container: {e}")
        return jsonify({"error": "Failed to start Gluetun container"}), 500


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
        return jsonify({"message": "Container destroyed"})
    except docker.errors.NotFound:
        return jsonify({"error": "Container not found"}), 404


@app.route("/status", methods=["GET"])
def get_status():
    return jsonify(RUNNING_CONTAINERS)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
