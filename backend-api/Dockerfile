# Use Python 3.12 slim Bookworm image
FROM python:3.12.11-slim-bookworm

# Set working directory
WORKDIR /app

# Environment and pip settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Create non-root user
RUN groupadd -r app && useradd -r -g app app

# Install system dependencies for browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    curl \
    xvfb \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and Camoufox profiles
RUN playwright install --with-deps chromium firefox webkit ffmpeg

# Clean up apt lists possibly left by Playwright deps installation
RUN rm -rf /var/lib/apt/lists/*

# Copy application files
COPY . .

# Ensure permissions for app code and Playwright browsers
RUN chown -R app:app /app /ms-playwright || true

# Expose API port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Start the API service
USER app
CMD ["uvicorn", "screenshot_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
