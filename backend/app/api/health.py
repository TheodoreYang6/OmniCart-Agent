import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.identity import require_admin

from app.core.config import (
    SERVICE_NAME,
    SERVICE_VERSION,
    USE_REDIS,
    USE_POSTGRES,
    USE_QDRANT,
)
from app.core.redis_client import health_check as redis_health

router = APIRouter()
logger = logging.getLogger(__name__)


async def _postgres_status() -> str:
    if not USE_POSTGRES:
        return "disabled"
    try:
        from sqlalchemy import text
        from app.core.database import get_session_sync
        factory = get_session_sync()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "unavailable"


def _qdrant_status() -> str:
    if not USE_QDRANT:
        return "disabled"
    try:
        from app.core.qdrant_client import get_qdrant
        client = get_qdrant()
        if client is None:
            return "unavailable"
        client.get_collections()
        return "connected"
    except Exception:
        return "unavailable"


@router.get("/api/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/api/health/ready")
async def readiness():
    from app.core.database import init_db
    from app.core.redis_client import get_redis

    async def probe(check):
        try:
            return "connected" if await asyncio.wait_for(check(), timeout=3) else "unavailable"
        except Exception as exc:
            logger.warning("readiness probe failed: %s", exc)
            return "unavailable"

    async def postgres():
        await init_db()
        return True

    async def qdrant():
        return await asyncio.to_thread(_qdrant_status) == "connected"

    async def redis():
        client = await get_redis()
        return bool(client and await client.ping())

    async def status(enabled, check):
        return await probe(check) if enabled else "disabled"

    pg, qd, rd = await asyncio.gather(
        status(USE_POSTGRES, postgres), status(USE_QDRANT, qdrant), status(USE_REDIS, redis),
    )
    ready = "unavailable" not in (pg, qd, rd)
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "postgres": pg, "qdrant": qd, "redis": rd},
        status_code=200 if ready else 503,
    )


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "postgres": await _postgres_status(),
        "qdrant": _qdrant_status(),
        "redis": "connected" if redis_health() else ("disabled" if not USE_REDIS else "unavailable"),
    }


@router.get("/api/cache/stats", dependencies=[Depends(require_admin)])
async def cache_stats():
    from app.core.cache import get_stats
    return {"redis": redis_health(), "stats": get_stats()}
