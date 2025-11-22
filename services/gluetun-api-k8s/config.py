"""
Configuration for Gluetun Kubernetes API
"""
import os

# Kubernetes namespace for Gluetun pods
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "default")

# Limit concurrent gluetun proxy instances
INSTANCE_LIMIT = int(os.environ.get("INSTANCE_LIMIT", 5))

# Optional preloaded Mullvad servers JSON (string)
SERVERS_JSON = os.environ.get("SERVERS_JSON")

# Optional path to Mullvad servers JSON file
SERVERS_FILE_PATH = os.environ.get("SERVERS_FILE_PATH")

# Default bundled servers file path (inside container)
DEFAULT_SERVERS_FILE_PATH = os.environ.get("DEFAULT_SERVERS_FILE_PATH", "/app/data/servers.json")

# Firewall settings for Gluetun proxy pods
FIREWALL_INPUT_PORTS = os.environ.get("FIREWALL_INPUT_PORTS", "8888")

# WireGuard credentials (required)
WIREGUARD_PRIVATE_KEY = os.environ.get("WIREGUARD_PRIVATE_KEY")
WIREGUARD_ADDRESSES = os.environ.get("WIREGUARD_ADDRESSES")

if not WIREGUARD_PRIVATE_KEY or not WIREGUARD_ADDRESSES:
    raise ValueError(
        "WIREGUARD_PRIVATE_KEY and WIREGUARD_ADDRESSES must be set as environment variables"
    )

