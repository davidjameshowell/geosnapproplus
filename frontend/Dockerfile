# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Default environment variables (overridable)
ENV BACKEND_URL=http://backend:8000 \
    DEBUG=false \
    PORT=5000 \
    POLL_INTERVAL_SECONDS=2 \
    MEDIA_DIR=/app/media

EXPOSE 5000

# Run with gunicorn (single worker to keep in-memory state consistent)
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:5000", "app:app"]
