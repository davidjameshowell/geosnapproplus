FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy test files
COPY . /app/

# Set the entrypoint to run tests
ENTRYPOINT ["python", "-m", "pytest", "test_frontend.py", "-v"]
