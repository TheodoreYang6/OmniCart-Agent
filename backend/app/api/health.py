from fastapi import APIRouter

from app.core.config import (
    SERVICE_NAME,
    SERVICE_VERSION,
    USE_REDIS,
    USE_POSTGRES,
    USE_QDRANT,
)
from app.core.redis_client import health_check as redis_health

router = APIRouter()


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


@router.get("/api/cache/stats")
async def cache_stats():
    from app.core.cache import get_stats
    return {"redis": redis_health(), "stats": get_stats()}
