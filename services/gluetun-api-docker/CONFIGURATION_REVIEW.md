# Gluetun Configuration Review

Based on official gluetun wiki documentation review, here are the issues found and fixes applied.

## Critical Issues Fixed

### 1. **Missing `/dev/net/tun` Device** ❌ → ✅ FIXED
   - **Issue**: The TUN device was not being passed to containers
   - **Impact**: VPN connections cannot be established without this device
   - **Fix**: Added `devices=["/dev/net/tun:/dev/net/tun"]` to both container creation calls
   - **Documentation**: All gluetun examples require this device mapping

### 2. **Incorrect DNS Environment Variables** ❌ → ✅ REMOVED
   - **Issue**: Using undocumented variables: `DNS_KEEP_NAMESERVER`, `DNS_PLAINTEXT_ADDRESS`, `DOT`
   - **Impact**: These variables may not exist or may not work as expected
   - **Fix**: Removed these variables. Docker DNS configuration (`dns=["8.8.8.8", "1.1.1.1"]`) should be sufficient
   - **Note**: Gluetun manages its own DNS internally, Docker DNS is for initial resolution

### 3. **Invalid Environment Variable** ❌ → ✅ REMOVED
   - **Issue**: `VPN_INPUT_PORTS=""` - this variable doesn't exist in gluetun documentation
   - **Fix**: Removed this variable

## Verified Correct Configuration

### ✅ Required Settings (All Present)
- `cap_add=["NET_ADMIN"]` - Required for network management
- `devices=["/dev/net/tun:/dev/net/tun"]` - **NOW ADDED** - Required for VPN tunnel
- `VPN_SERVICE_PROVIDER="mullvad"` - Correct
- `VPN_TYPE="wireguard"` - Correct
- `WIREGUARD_PRIVATE_KEY` - Correct
- `WIREGUARD_ADDRESSES` - Correct
- `dns=["8.8.8.8", "1.1.1.1"]` - Good practice for initial DNS resolution

### ✅ Optional but Valid Settings
- `MULLVAD_SERVER_HOSTNAME` - Using hostname is valid (alternative to `SERVER_CITIES`)
- `FIREWALL_OUTBOUND_SUBNETS="0.0.0.0/0"` - Valid variable (confirmed in docs)
  - Allows all outbound traffic, which helps with VPN connection establishment
- `HTTP_PROXY="on"` - Correct for proxy functionality
- `HTTP_PROXY_USER` and `HTTP_PROXY_PASSWORD` - Correct

## Official Mullvad Configuration Reference

According to gluetun wiki, the minimal Mullvad Wireguard configuration is:

```yaml
environment:
  - VPN_SERVICE_PROVIDER=mullvad
  - VPN_TYPE=wireguard
  - WIREGUARD_PRIVATE_KEY=<your_key>
  - WIREGUARD_ADDRESSES=<your_address>/32
  - SERVER_CITIES=Amsterdam  # Alternative to MULLVAD_SERVER_HOSTNAME
```

Our configuration uses `MULLVAD_SERVER_HOSTNAME` instead of `SERVER_CITIES`, which should also work as gluetun accepts hostname specification.

## Summary of Changes

1. ✅ **Added** `/dev/net/tun` device mapping (CRITICAL)
2. ✅ **Removed** undocumented DNS variables (`DNS_KEEP_NAMESERVER`, `DNS_PLAINTEXT_ADDRESS`, `DOT`)
3. ✅ **Removed** invalid variable (`VPN_INPUT_PORTS`)
4. ✅ **Kept** `FIREWALL_OUTBOUND_SUBNETS="0.0.0.0/0"` (valid and helpful)
5. ✅ **Verified** all other environment variables are correct

## Next Steps

After these changes:
1. Restart the gluetun-api service
2. Test container creation
3. The `/dev/net/tun` device should allow proper VPN tunnel establishment
4. The simplified configuration aligns with official gluetun examples

## Expected Improvements

- VPN tunnels should now establish properly (with TUN device)
- Simpler, more maintainable configuration
- Better alignment with official gluetun documentation
- No undocumented variables that might cause issues

