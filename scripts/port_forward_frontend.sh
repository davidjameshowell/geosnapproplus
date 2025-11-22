#!/bin/bash
echo "Port forwarding frontend service to localhost:5000..."
kubectl -n geosnap-e2e port-forward svc/frontend 5000:5000

