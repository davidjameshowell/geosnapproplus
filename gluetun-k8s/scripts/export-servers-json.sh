#!/bin/bash
# Export Mullvad server list JSON using the upstream Gluetun Docker image.
#
# Requirements:
#   - Docker installed and running
#   - Valid Mullvad WireGuard credentials supplied through environment variables:
#       WIREGUARD_PRIVATE_KEY
#       WIREGUARD_ADDRESSES
#   - Access to /dev/net/tun (may require running with sudo on some systems)
#
# Usage:
#   export WIREGUARD_PRIVATE_KEY="..."
#   export WIREGUARD_ADDRESSES="..."
#   ./scripts/export-servers-json.sh ./servers.json
#

set -euo pipefail

OUTPUT_PATH="${1:-servers.json}"

if [[ -z "${WIREGUARD_PRIVATE_KEY:-}" || -z "${WIREGUARD_ADDRESSES:-}" ]]; then
    echo "ERROR: WIREGUARD_PRIVATE_KEY and WIREGUARD_ADDRESSES must be set in the environment." >&2
    exit 1
fi

echo "Exporting Mullvad server list to '${OUTPUT_PATH}'..."

docker run --rm \
    --cap-add=NET_ADMIN \
    --device=/dev/net/tun:/dev/net/tun \
    -e VPN_SERVICE_PROVIDER=mullvad \
    -e VPN_TYPE=wireguard \
    -e WIREGUARD_PRIVATE_KEY="$WIREGUARD_PRIVATE_KEY" \
    -e WIREGUARD_ADDRESSES="$WIREGUARD_ADDRESSES" \
    --entrypoint /bin/sh \
    qmcgaw/gluetun:latest \
    -c 'set -eu
        cleanup() {
            kill "$PID" 2>/dev/null || true
        }
        /gluetun-entrypoint >/tmp/gluetun-entrypoint.log 2>&1 &
        PID=$!
        trap cleanup EXIT
        for i in $(seq 1 60); do
            if [ -f /gluetun/servers.json ]; then
                cat /gluetun/servers.json
                exit 0
            fi
            sleep 2
        done
        echo "Timed out waiting for servers.json" >&2
        exit 1' \
    > "$OUTPUT_PATH"

echo "Server list saved to '${OUTPUT_PATH}'."

