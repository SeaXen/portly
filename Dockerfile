# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY portly/frontend/package*.json ./
RUN npm ci
COPY portly/frontend/ ./
RUN npm run build

# Stage 2: Runtime Image
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies (net-tools, procps, curl, docker CLI & compose)
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    net-tools \
    curl \
    docker-cli \
    docker-compose \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application backend and built frontend
COPY portly/ ./portly/
COPY --from=frontend-builder /app/frontend/dist ./portly/frontend/dist

# Expose Portly default port
EXPOSE 5533

ENV PORTLY_PORT=5533 \
    PORTLY_HOST=0.0.0.0 \
    PORTLY_MODE=server \
    PORTLY_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

# Create non-root user portly (UID/GID 1000 matching DEPLOYMENT.md) and set up data directory permissions
RUN groupadd -g 1000 portly && useradd -u 1000 -g portly -d /app -s /sbin/nologin portly && \
    mkdir -p /app/data && chown -R portly:portly /app

VOLUME ["/app/data"]

USER portly

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f "http://127.0.0.1:${PORTLY_PORT}/api/health" || exit 1

CMD ["sh", "-c", "python -m portly run --port \"${PORTLY_PORT}\" --host \"${PORTLY_HOST}\" --mode \"${PORTLY_MODE}\""]
