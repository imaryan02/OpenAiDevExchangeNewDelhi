# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8002

WORKDIR /app

# Install system utilities for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy backend dependencies
COPY backend/pyproject.toml backend/requirements.lock* /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.lock

# Copy backend application source
COPY backend/app /app/app
RUN pip install --no-cache-dir -e . --no-deps

# Expose default container port
EXPOSE 8002

# Healthcheck against liveness endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health/live || exit 1

# Run Uvicorn listening on 0.0.0.0 and dynamically bound PORT
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
