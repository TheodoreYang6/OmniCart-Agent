#!/bin/bash
set -e

echo "==> OmniCart Agent Container Startup"

# 等待 PostgreSQL 就绪
if [ -n "$DATABASE_URL" ]; then
    echo "--> Waiting for PostgreSQL..."
    until python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('${DATABASE_URL//+asyncpg/}'))" 2>/dev/null; do
        sleep 2
    done
    echo "--> PostgreSQL ready, running migrations..."
    cd /app && python -m alembic upgrade head || echo "--> Migration skipped (tables exist)"
fi

echo "--> Starting Uvicorn..."
cd /app/backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8006 --log-level info --loop asyncio
