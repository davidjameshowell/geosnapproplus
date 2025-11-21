# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir gevent

# Copy application code
COPY . /app

# Create non-root user and media directory with proper permissions
RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser appuser && \
    mkdir -p /app/media && \
    chown -R appuser:appuser /app

# Default environment variables (overridable)
ENV BACKEND_URL=http://backend:8000 \
    DEBUG=false \
    PORT=5000 \
    POLL_INTERVAL_SECONDS=2 \
    MEDIA_DIR=/app/media

# Switch to non-root user
USER appuser

EXPOSE 5000

# Run with gunicorn using gthread (compatible with flask-sock and standard threads)
CMD ["gunicorn", "--workers", "1", "--threads", "10", "--timeout", "120", "--bind", "0.0.0.0:5000", "app:app"]
