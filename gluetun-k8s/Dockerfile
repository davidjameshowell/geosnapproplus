FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY k8s_manager.py .
COPY config.py .
COPY data/ ./data/

# Expose API port
EXPOSE 8001

# Run the application
CMD ["python", "app.py"]

