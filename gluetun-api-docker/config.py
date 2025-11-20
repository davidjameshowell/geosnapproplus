import os

# Limit concurrent gluetun proxy instances
# Since screenshot API processes tasks sequentially, we only need a small buffer
# to handle cleanup delays and potential race conditions
INSTANCE_LIMIT = int(os.environ.get("INSTANCE_LIMIT", 2))
WIREGUARD_PRIVATE_KEY = os.environ.get("WIREGUARD_PRIVATE_KEY")
WIREGUARD_ADDRESSES = os.environ.get("WIREGUARD_ADDRESSES")
