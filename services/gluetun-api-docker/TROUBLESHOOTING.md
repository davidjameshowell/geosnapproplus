# Gluetun Container Restart Investigation

## Problem Identified

The gluetun VPN containers are restarting consistently due to **DNS resolution failures** during healthchecks.

### Root Cause

1. **DNS Resolution Failure**: The container cannot resolve `cloudflare.com` (used for healthchecks)
   - Error: `lookup cloudflare.com: i/o timeout`
   - This prevents the healthcheck from passing, causing gluetun to restart the VPN connection

2. **Missing DNS Configuration**: The containers were created without explicit DNS server configuration
   - Docker inspect showed `"Dns": null`
   - No DNS servers were configured for initial name resolution

3. **Secondary Issue**: Firewall/iptables parsing errors (non-critical)
   - Errors about parsing protocol "all" in iptables rules
   - These are warnings and don't prevent VPN from working

## Solution Applied

### Changes Made to `app.py`

1. **Added DNS Server Configuration**:
   - Added `HostConfig` with `dns=["8.8.8.8", "1.1.1.1"]` to provide DNS servers for initial resolution
   - This ensures containers can resolve hostnames before and during VPN connection

2. **Added DNS Environment Variables**:
   - `DNS_KEEP_NAMESERVER=on`: Keeps the initial DNS servers (from Docker HostConfig) until VPN is fully connected

3. **Updated Container Creation**:
   - Both `get_mullvad_servers()` and `start_gluetun()` functions now use `HostConfig` properly
   - DNS configuration is applied to all gluetun containers

### Code Changes

```python
from docker.types import HostConfig

host_config = HostConfig(
    cap_add=["NET_ADMIN"],
    dns=["8.8.8.8", "1.1.1.1"],  # Configure DNS servers
    port_bindings={"8888/tcp": None},  # For start_gluetun only
)

container = client.containers.run(
    "qmcgaw/gluetun",
    host_config=host_config,
    environment={
        # ... existing env vars ...
        "DNS_KEEP_NAMESERVER": "on",
    },
    # ...
)
```

## Testing the Fix

To verify the fix works:

1. **Restart the gluetun-api service** to load the new code:
   ```bash
   docker-compose restart gluetun-api
   ```

2. **Stop existing problematic containers**:
   ```bash
   docker ps -a | grep gluetun-
   # Note the container IDs, then stop them via the API or docker stop
   ```

3. **Start a new container** and monitor logs:
   ```bash
   # Start via API
   curl -X POST http://localhost:8001/start \
     -H "Content-Type: application/json" \
     -d '{"country": "USA", "city": "New York"}'
   
   # Watch logs
   docker logs -f <container-name>
   ```

4. **Verify DNS resolution works**:
   - Look for successful healthcheck messages
   - Should see successful VPN connection without DNS timeout errors

## Updated Issue Discovery

After applying DNS configuration fixes, testing revealed a **deeper networking problem**:

### Root Cause Identified

The containers **cannot reach external IP addresses at all**:
- `ping 8.8.8.8` fails with 100% packet loss
- `nslookup cloudflare.com` times out
- This is a Docker/WSL2 networking issue, not just DNS configuration

### Impact

Without internet connectivity, gluetun containers cannot:
- Connect to VPN servers
- Resolve DNS queries
- Perform healthchecks

This explains why containers restart continuously - they can't establish VPN connections because they can't reach the internet.

### Additional Configuration Applied

Added firewall and DNS settings:
- `FIREWALL_OUTBOUND_SUBNETS=0.0.0.0/0` - Allow outbound traffic for VPN connection
- `DNS_PLAINTEXT_ADDRESS=1.1.1.1` - Use plain DNS instead of DNS over TLS
- `DOT=off` - Disable DNS over TLS to avoid startup delays

## Expected Behavior After Fix

- ✅ Containers should start and remain stable
- ✅ DNS lookups should succeed (no "i/o timeout" errors)
- ✅ Healthchecks should pass
- ✅ VPN connections should establish and stay connected
- ⚠️ Firewall warnings may still appear but won't cause restarts

**However**, if the underlying Docker/WSL2 networking issue persists, containers still won't be able to connect to VPN servers.

## Additional Notes

- The fix addresses the immediate DNS resolution issue
- If problems persist, check:
  - Host network connectivity
  - Firewall rules on the host
  - WSL2 networking configuration
  - VPN credentials validity

## Monitoring

Monitor container status with:
```bash
# Check container health
docker ps | grep gluetun

# View logs for errors
docker logs --tail 50 <container-name>

# Check DNS resolution inside container
docker exec <container-name> nslookup cloudflare.com
```

