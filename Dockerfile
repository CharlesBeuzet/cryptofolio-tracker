# syntax=docker/dockerfile:1
# Single-container image for Raspberry Pi (linux/arm64): nginx + FastAPI.

FROM --platform=linux/arm64 node:20-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=linux/arm64 python:3.11-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY settings/config.example.yaml /app/settings/config.example.yaml
COPY --from=frontend-build /frontend/dist /app/frontend/dist
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/settings \
    && rm -f /etc/nginx/sites-enabled/default

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
