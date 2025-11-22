# Gluetun API Documentation

A REST API service for managing Gluetun VPN containers. This API allows you to discover Mullvad VPN servers and create managed VPN proxy containers.

## Table of Contents

- [Overview](#overview)
- [Base URL](#base-url)
- [Endpoints](#endpoints)
  - [GET /servers](#get-servers)
  - [GET /locations](#get-locations)
  - [POST /servers/refresh](#post-serversrefresh)
  - [POST /start](#post-start)
  - [POST /stop](#post-stop)
  - [POST /destroy](#post-destroy)
  - [GET /status](#get-status)
- [Examples](#examples)
- [Error Responses](#error-responses)

## Overview

The Gluetun API provides a simple interface to:
- Discover available Mullvad Wireguard VPN servers
- Start VPN proxy containers with HTTP proxy support
- Manage running VPN containers (stop, destroy, check status)

All containers run in isolated Docker containers and provide HTTP proxy access on random ports.

## Base URL

By default, the API runs at:
```
http://localhost:8001
```

## Endpoints

### GET /servers

Retrieve the list of available Mullvad Wireguard VPN servers.

**Note:** Server data is cached in memory after the first request. Use the `force` parameter to refresh the cache when needed.

#### Query Parameters

- `country` (optional): Filter servers by country name (case-insensitive, partial match)
- `city` (optional): Filter servers by city name (case-insensitive, partial match)
- `force` (optional): Force refresh the server cache before returning results (values: `true`, `1`, or `yes`)

#### Response

Returns a JSON object where keys are server identifiers and values are server objects:

```json
{
  "usa-new-york-ny-us-nyc-wg-301": {
    "city": "New York",
    "country": "USA",
    "hostname": "us-nyc-wg-301",
    "ips": ["103.204.123.130", "2a04:27c0:0:c::f001"],
    "isp": "iRegister",
    "vpn": "wireguard",
    "wgpubkey": "rWiQxq5lAWD8v/bws9ITSAvThyZW8cR2x+Ins9ZvvRo="
  },
  ...
}
```

#### Examples

**Get all servers:**
```bash
curl http://localhost:8001/servers
```

**Filter by country:**
```bash
curl "http://localhost:8001/servers?country=USA"
curl "http://localhost:8001/servers?country=canada"
```

**Filter by city:**
```bash
curl "http://localhost:8001/servers?city=New%20York"
curl "http://localhost:8001/servers?city=toronto"
```

**Filter by both country and city:**
```bash
curl "http://localhost:8001/servers?country=USA&city=New%20York"
curl "http://localhost:8001/servers?country=Canada&city=Toronto"
```

**Force refresh cache:**
```bash
curl "http://localhost:8001/servers?force=true"
curl "http://localhost:8001/servers?country=USA&force=true"
```

**Pretty print with jq:**
```bash
curl -s http://localhost:8001/servers | jq '. | length'  # Count servers
curl -s "http://localhost:8001/servers?country=USA" | jq 'keys | length'  # Count US servers
```

---

### GET /locations

Get a friendly list of all locations organized by country and city. This endpoint is designed for frontend use to display location selection options.

**Note:** Server data is cached in memory after the first request. Use the `force` parameter to refresh the cache when needed.

#### Query Parameters

- `force` (optional): Force refresh the server cache before returning results (values: `true`, `1`, or `yes`)

#### Response

Returns a JSON object with a hierarchical structure:

```json
{
  "countries": [
    {
      "name": "United States",
      "city_count": 15,
      "total_servers": 45,
      "cities": [
        {
          "name": "New York",
          "server_count": 5,
          "sample_hostname": "us-nyc-wg-301"
        },
        {
          "name": "Los Angeles",
          "server_count": 3,
          "sample_hostname": "us-lax-wg-301"
        }
      ]
    },
    {
      "name": "Canada",
      "city_count": 8,
      "total_servers": 24,
      "cities": [
        {
          "name": "Toronto",
          "server_count": 4,
          "sample_hostname": "ca-tor-wg-301"
        }
      ]
    }
  ],
  "total_countries": 50,
  "total_cities": 200,
  "total_servers": 532
}
```

#### Examples

**Get all locations:**
```bash
curl http://localhost:8001/locations
```

**Force refresh cache:**
```bash
curl "http://localhost:8001/locations?force=true"
```

**Pretty print with jq:**
```bash
curl -s http://localhost:8001/locations | jq '.countries[] | {name: .name, cities: .cities | length}'
```

**List all countries:**
```bash
curl -s http://localhost:8001/locations | jq '.countries[].name'
```

**List cities in a specific country:**
```bash
curl -s http://localhost:8001/locations | jq '.countries[] | select(.name == "United States") | .cities[].name'
```

---

### POST /servers/refresh

Explicitly refresh the server cache by fetching the latest server list from Mullvad.

This endpoint forces a refresh of the Mullvad server list by starting a temporary Gluetun container and fetching the latest server data. Use this when you need to ensure you have the most up-to-date server information.

#### Response

Success (200):
```json
{
  "message": "Server cache refreshed",
  "server_count": 532
}
```

Error (500):
```json
{
  "error": "Failed to refresh server cache"
}
```

#### Examples

```bash
# Refresh the server cache
curl -X POST http://localhost:8001/servers/refresh

# With jq for pretty output
curl -s -X POST http://localhost:8001/servers/refresh | jq
```

---

### POST /start

Start a new Gluetun VPN container.

#### Request Body

The request body accepts one of the following options:

**Option 1: Specify server by key**
```json
{
  "server": "usa-new-york-ny-us-nyc-wg-301"
}
```

**Option 2: Specify by country and/or city**
```json
{
  "country": "USA",
  "city": "New York"
}
```

Or just country:
```json
{
  "country": "Canada"
}
```

Or just city:
```json
{
  "city": "Toronto"
}
```

#### Response

Success (200):
```json
{
  "id": "40933c69-d9c1-423f-affe-cbf0a0e3f860",
  "proxy": "http://3lauSfsy25:iThlGEcdMr@localhost:46415"
}
```

- `id`: Container identifier for managing this container
- `proxy`: HTTP proxy URL with authentication credentials

#### Error Responses

- `400`: Invalid server or no matching server found
- `429`: Instance limit reached

#### Examples

**Start by server key:**
```bash
curl -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"server": "usa-new-york-ny-us-nyc-wg-301"}'
```

**Start by country and city:**
```bash
curl -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA", "city": "New York"}'
```

**Start by country only:**
```bash
curl -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"country": "Canada"}'
```

**Start by city only:**
```bash
curl -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"city": "Toronto"}'
```

**Using the proxy:**
```bash
# Start container
RESPONSE=$(curl -s -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA", "city": "New York"}')

# Extract proxy URL
PROXY=$(echo $RESPONSE | jq -r '.proxy')

# Use proxy for a request
curl -x $PROXY https://api.ipify.org?format=json
```

---

### POST /stop

Stop a running VPN container. The container remains in the system but is stopped.

#### Request Body

```json
{
  "id": "40933c69-d9c1-423f-affe-cbf0a0e3f860"
}
```

#### Response

Success (200):
```json
{
  "message": "Container stopped"
}
```

#### Error Responses

- `404`: Container not found

#### Examples

```bash
# Stop a container
curl -X POST http://localhost:8001/stop \
  -H "Content-Type: application/json" \
  -d '{"id": "40933c69-d9c1-423f-affe-cbf0a0e3f860"}'

# With jq for pretty output
curl -s -X POST http://localhost:8001/stop \
  -H "Content-Type: application/json" \
  -d '{"id": "40933c69-d9c1-423f-affe-cbf0a0e3f860"}' | jq
```

---

### POST /destroy

Destroy a VPN container. This stops and removes the container completely.

#### Request Body

```json
{
  "id": "40933c69-d9c1-423f-affe-cbf0a0e3f860"
}
```

#### Response

Success (200):
```json
{
  "message": "Container destroyed"
}
```

#### Error Responses

- `404`: Container not found

#### Examples

```bash
# Destroy a container
curl -X POST http://localhost:8001/destroy \
  -H "Content-Type: application/json" \
  -d '{"id": "40933c69-d9c1-423f-affe-cbf0a0e3f860"}'

# With jq for pretty output
curl -s -X POST http://localhost:8001/destroy \
  -H "Content-Type: application/json" \
  -d '{"id": "40933c69-d9c1-423f-affe-cbf0a0e3f860"}' | jq
```

---

### GET /status

Get the status of all running VPN containers.

#### Response

Returns a JSON object where keys are container IDs and values are container information:

```json
{
  "40933c69-d9c1-423f-affe-cbf0a0e3f860": {
    "container_id": "abc123...",
    "container_name": "gluetun-40933c69-d9c1-423f-affe-cbf0a0e3f860",
    "server": "usa-new-york-ny-us-nyc-wg-301",
    "username": "3lauSfsy25",
    "password": "iThlGEcdMr",
    "port": "46415"
  },
  ...
}
```

#### Examples

```bash
# Get all container statuses
curl http://localhost:8001/status

# Count running containers
curl -s http://localhost:8001/status | jq '. | length'

# List container IDs
curl -s http://localhost:8001/status | jq 'keys'

# Get details for a specific container
curl -s http://localhost:8001/status | jq '.["40933c69-d9c1-423f-affe-cbf0a0e3f860"]'

# Pretty print all containers
curl -s http://localhost:8001/status | jq
```

---

## Examples

### Complete Workflow

**1. List available servers:**
```bash
curl -s http://localhost:8001/servers | jq 'keys | length'
```

**2. Filter servers by location:**
```bash
# Find servers in USA
curl -s "http://localhost:8001/servers?country=USA" | jq 'keys | length'

# Find servers in New York
curl -s "http://localhost:8001/servers?country=USA&city=New%20York" | jq 'keys'
```

**3. Start a VPN container:**
```bash
# Start by country and city
RESPONSE=$(curl -s -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA", "city": "New York"}')

# Extract container ID and proxy
CONTAINER_ID=$(echo $RESPONSE | jq -r '.id')
PROXY=$(echo $RESPONSE | jq -r '.proxy')

echo "Container ID: $CONTAINER_ID"
echo "Proxy: $PROXY"
```

**4. Check container status:**
```bash
curl -s http://localhost:8001/status | jq
```

**5. Test the proxy:**
```bash
# Test proxy with curl
curl -x $PROXY https://api.ipify.org?format=json

# Test proxy with HTTP_PROXY environment variable
export HTTP_PROXY=$PROXY
curl https://api.ipify.org?format=json
```

**6. Stop the container:**
```bash
curl -X POST http://localhost:8001/stop \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$CONTAINER_ID\"}"
```

**7. Destroy the container:**
```bash
curl -X POST http://localhost:8001/destroy \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$CONTAINER_ID\"}"
```

### Quick Start Script

```bash
#!/bin/bash

# Start a VPN in New York
echo "Starting VPN in New York..."
RESPONSE=$(curl -s -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA", "city": "New York"}')

CONTAINER_ID=$(echo $RESPONSE | jq -r '.id')
PROXY=$(echo $RESPONSE | jq -r '.proxy')

if [ "$CONTAINER_ID" != "null" ]; then
  echo "✓ VPN started: $CONTAINER_ID"
  echo "✓ Proxy: $PROXY"
  
  # Test the proxy
  echo "Testing proxy..."
  curl -x $PROXY -s https://api.ipify.org?format=json | jq
  
  # Clean up
  read -p "Press Enter to destroy container..."
  curl -s -X POST http://localhost:8001/destroy \
    -H "Content-Type: application/json" \
    -d "{\"id\": \"$CONTAINER_ID\"}" | jq
else
  echo "✗ Failed to start VPN"
  echo $RESPONSE | jq
fi
```

---

## Error Responses

All endpoints return JSON error responses in the following format:

```json
{
  "error": "Error message description"
}
```

### Common Error Codes

- `400 Bad Request`: Invalid request parameters
  - "Invalid server"
  - "No server found for country 'xxx' and city 'yyy'"
  - "Must provide either 'server' or 'country'/'city' parameters"

- `404 Not Found`: Resource not found
  - "Container not found"

- `429 Too Many Requests`: Rate limiting
  - "Instance limit reached"

### Error Handling Examples

```bash
# Check if request was successful
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST http://localhost:8001/start \
  -H "Content-Type: application/json" \
  -d '{"country": "InvalidCountry"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
  echo "Success: $BODY" | jq
else
  echo "Error ($HTTP_CODE): $BODY" | jq
fi
```

---

## Configuration

The API can be configured via environment variables in `deploy/docker-compose.yml`:

- `WIREGUARD_PRIVATE_KEY`: Your Mullvad Wireguard private key
- `WIREGUARD_ADDRESSES`: Your Wireguard IP address (e.g., "10.68.50.98/32")
- `INSTANCE_LIMIT`: Maximum number of concurrent VPN containers (default: 1)
- `LOG_LEVEL`: Logging level (default: INFO)

---

## Docker Compose

To start the API service:

```bash
docker-compose -f deploy/docker-compose.yml up -d gluetun-api
```

To view logs:

```bash
docker-compose -f deploy/docker-compose.yml logs -f gluetun-api
```

To rebuild and restart:

```bash
docker-compose -f deploy/docker-compose.yml build gluetun-api
docker-compose -f deploy/docker-compose.yml up -d gluetun-api
```

---

## Notes

- **Server Caching:** The server list is cached in memory after the first request. This means:
  - The first request to `/servers` or `/locations` may take up to 60 seconds as it initializes and fetches the server list from a temporary Gluetun container
  - Subsequent requests are much faster as they use the cached data
  - To refresh the cache, use the `force=true` query parameter on `/servers` or `/locations`, or call the `/servers/refresh` endpoint
- Container ports are assigned randomly by Docker
- Proxy credentials are randomly generated for each container
- All country and city filters are case-insensitive and support partial matching
---

## Docker Compose

To start the API service:

```bash
docker-compose up -d gluetun-api
```

To view logs:

```bash
docker-compose logs -f gluetun-api
```

To rebuild and restart:

```bash
docker-compose build gluetun-api
docker-compose up -d gluetun-api
```

