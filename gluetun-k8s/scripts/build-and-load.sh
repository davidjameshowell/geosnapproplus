#!/bin/bash
# Build and load Docker image into kind cluster

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVERS_JSON_PATH="$PROJECT_ROOT/data/servers.json"

if [[ -n "${WIREGUARD_PRIVATE_KEY:-}" && -n "${WIREGUARD_ADDRESSES:-}" ]]; then
  echo "Updating bundled Mullvad server list..."
  "$SCRIPT_DIR/export-servers-json.sh" "$SERVERS_JSON_PATH"
else
  echo "WIREGUARD_PRIVATE_KEY / WIREGUARD_ADDRESSES not set; using existing bundled servers.json"
fi

echo "Building Docker image..."
docker build -t gluetun-k8s-api:latest .

echo "Loading image into kind cluster..."
kind load docker-image gluetun-k8s-api:latest

echo "Image successfully loaded into kind cluster!"

