#!/bin/sh
set -eu

mkdir -p /app/settings

# Start nginx in the background; FastAPI stays on loopback only.
nginx

cd /app/backend
exec python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
