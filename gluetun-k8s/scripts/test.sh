#!/bin/bash
# Run tests against the Gluetun K8s API

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if API is accessible
API_URL="${GLUETUN_K8S_API_URL:-http://localhost:30801}"

echo "Testing API at: $API_URL"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "pytest not found. Installing test dependencies..."
    pip install -r requirements.txt
fi

# Run tests
echo "Running test suite..."
cd "$SCRIPT_DIR/.."
pytest tests/ -v --tb=short

echo ""
echo "Tests complete!"

