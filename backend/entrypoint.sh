#!/bin/bash
set -euo pipefail

cd /app
if [ -n "${DATABASE_URL:-}" ]; then
    python -m alembic upgrade head
fi

exec python -m uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port 8006 --log-level info --loop asyncio
