# Gluetun Kubernetes API - Examples

This directory contains example scripts and usage patterns for the Gluetun Kubernetes API.

## Python Example

### api_usage.py

A complete demonstration of the API functionality including:
- Health checks
- Listing servers and locations
- Starting VPN pods
- Checking pod status
- Destroying pods

**Usage:**

```bash
# Install requests if needed
pip install requests

# Run the example
python examples/api_usage.py
```

The script will:
1. Check API health
2. List available servers
3. Start a VPN pod in the USA
4. Show pod status
5. Wait for user input
6. Clean up the pod

## Shell Script Examples

### Simple Health Check

```bash
#!/bin/bash
API_URL="http://localhost:30801"

response=$(curl -s "$API_URL/health")
echo "Health check: $response"
```

### List Servers with jq

```bash
#!/bin/bash
API_URL="http://localhost:30801"

# Get all USA servers
curl -s "$API_URL/servers?country=USA" | jq -r 'keys[]'

# Count servers by country
curl -s "$API_URL/servers" | jq -r 'group_by(.country) | map({country: .[0].country, count: length}) | .[]'
```

### Start and Use a VPN Pod

```bash
#!/bin/bash
API_URL="http://localhost:30801"

# Start a VPN pod
response=$(curl -s -X POST "$API_URL/start" \
  -H "Content-Type: application/json" \
  -d '{"country": "USA"}')

# Extract details
pod_id=$(echo "$response" | jq -r '.id')
proxy_url=$(echo "$response" | jq -r '.proxy')

echo "VPN Pod started:"
echo "  ID: $pod_id"
echo "  Proxy: $proxy_url"

# Wait for pod to be ready
sleep 10

# Test the proxy (from within cluster)
# kubectl run -it --rm test-curl --image=curlimages/curl -n gluetun-system -- \
#   curl -x "$proxy_url" http://ifconfig.me

# Clean up
echo "Cleaning up..."
curl -s -X POST "$API_URL/destroy" \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$pod_id\"}"

echo "Done!"
```

## curl Commands

### Health Check

```bash
curl http://localhost:30801/health
```

### List All Servers

```bash
curl http://localhost:30801/servers | jq
```

### Filter Servers by Country

```bash
curl "http://localhost:30801/servers?country=USA" | jq
```

### Get Locations

```bash
curl http://localhost:30801/locations | jq
```

### Start VPN Pod by Country

```bash
curl -X POST http://localhost:30801/start \
  -H "Content-Type: application/json" \
  -d '{"country": "USA"}' | jq
```

### Start VPN Pod by Server

```bash
curl -X POST http://localhost:30801/start \
  -H "Content-Type: application/json" \
  -d '{"server": "usa-new-york-ny-us-nyc-wg-301"}' | jq
```

### Get Status

```bash
curl http://localhost:30801/status | jq
```

### Destroy Pod

```bash
POD_ID="your-pod-id-here"
curl -X POST http://localhost:30801/destroy \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$POD_ID\"}" | jq
```

### Refresh Server Cache

```bash
curl -X POST http://localhost:30801/servers/refresh | jq
```

## Advanced Usage

### Start Multiple VPN Pods

```bash
#!/bin/bash
API_URL="http://localhost:30801"

# Start 3 VPN pods in different countries
countries=("USA" "Germany" "Sweden")

for country in "${countries[@]}"; do
  echo "Starting VPN pod in $country..."
  curl -s -X POST "$API_URL/start" \
    -H "Content-Type: application/json" \
    -d "{\"country\": \"$country\"}" | jq -r '.id'
  sleep 2
done

# Show all running pods
curl -s "$API_URL/status" | jq
```

### Monitor Pod Status

```bash
#!/bin/bash
API_URL="http://localhost:30801"

while true; do
  clear
  echo "=== VPN Pod Status ==="
  curl -s "$API_URL/status" | jq -r 'to_entries[] | "\(.key): \(.value.server) (\(.value.status))"'
  sleep 5
done
```

### Cleanup All Pods

```bash
#!/bin/bash
API_URL="http://localhost:30801"

# Get all running pod IDs
pod_ids=$(curl -s "$API_URL/status" | jq -r 'keys[]')

# Destroy each pod
for pod_id in $pod_ids; do
  echo "Destroying pod: $pod_id"
  curl -s -X POST "$API_URL/destroy" \
    -H "Content-Type: application/json" \
    -d "{\"id\": \"$pod_id\"}"
  sleep 1
done

echo "All pods destroyed"
```

## Using from Other Languages

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API_URL = 'http://localhost:30801';

async function startVpnPod(country) {
  try {
    const response = await axios.post(`${API_URL}/start`, {
      country: country
    });
    console.log('VPN Pod started:', response.data);
    return response.data;
  } catch (error) {
    console.error('Error starting VPN pod:', error.response?.data || error.message);
    return null;
  }
}

async function main() {
  const pod = await startVpnPod('USA');
  if (pod) {
    console.log('Use proxy:', pod.proxy);
    
    // Do work with the proxy...
    
    // Clean up
    await axios.post(`${API_URL}/destroy`, { id: pod.id });
  }
}

main();
```

### Go

```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
)

const apiURL = "http://localhost:30801"

type StartRequest struct {
    Country string `json:"country"`
}

type StartResponse struct {
    ID      string `json:"id"`
    Proxy   string `json:"proxy"`
    PodName string `json:"pod_name"`
    PodIP   string `json:"pod_ip"`
}

func startVpnPod(country string) (*StartResponse, error) {
    payload := StartRequest{Country: country}
    data, _ := json.Marshal(payload)
    
    resp, err := http.Post(apiURL+"/start", "application/json", bytes.NewBuffer(data))
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    
    body, _ := io.ReadAll(resp.Body)
    
    var result StartResponse
    json.Unmarshal(body, &result)
    
    return &result, nil
}

func main() {
    pod, err := startVpnPod("USA")
    if err != nil {
        panic(err)
    }
    
    fmt.Printf("VPN Pod started: %s\n", pod.ID)
    fmt.Printf("Proxy URL: %s\n", pod.Proxy)
}
```

## Testing from Within Cluster

To test the proxy from within the Kubernetes cluster:

```bash
# Create a test pod
kubectl run -it --rm test-pod --image=curlimages/curl -n gluetun-system -- sh

# Inside the pod, use the proxy
# (Replace with actual proxy URL from /start response)
curl -x http://username:password@10.244.0.5:8888 http://ifconfig.me
curl -x http://username:password@10.244.0.5:8888 https://ipapi.co/json
```

## Tips

1. **API URL**: Adjust `API_URL` based on your environment:
   - kind: `http://localhost:30801`
   - Port-forward: `http://localhost:8001`
   - Ingress: `https://gluetun-api.yourdomain.com`

2. **Timeouts**: Pod creation can take 60-90 seconds. Adjust timeouts accordingly.

3. **Instance Limits**: Check the configured `INSTANCE_LIMIT` if you get 429 errors.

4. **Cleanup**: Always destroy pods when done to free up resources.

5. **Proxy Access**: The proxy is only accessible from within the Kubernetes cluster network.

## More Information

- [Main README](../README.md)
- [Deployment Guide](../DEPLOYMENT_GUIDE.md)
- [Quick Start](../QUICK_START.md)

