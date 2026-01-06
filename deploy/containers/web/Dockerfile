# Optimized Web Container - Minimal size, production-ready
# Multi-stage build for smallest possible image

# Stage 1: Build dependencies
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements
COPY requirements-base.txt requirements-web.txt /tmp/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements-web.txt

# Stage 2: Final minimal image
FROM python:3.12-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    libmagic1 \
    curl \
    xmlsec1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy application code (exclude unnecessary files via .dockerignore)
COPY --chown=appuser:appuser . .

# Copy entrypoint script
COPY --chown=appuser:appuser deploy/containers/entrypoint-web.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create necessary directories
RUN mkdir -p /app/static /app/media /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=depot.settings \
    SERVER_ROLE=web \
    PATH="/opt/venv/bin:$PATH"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health/ -H "Host: naaccord.pequod.sh" || exit 1

# Use flexible entrypoint
ENTRYPOINT ["/entrypoint.sh"]