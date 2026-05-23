from fastapi import APIRouter

from app.core.config import SERVICE_NAME, SERVICE_VERSION, USE_REDIS
from app.core.redis_client import health_check as redis_health

router = APIRouter()


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "redis": "connected" if redis_health() else ("disabled" if not USE_REDIS else "unavailable"),
    }


@router.get("/api/cache/stats")
async def cache_stats():
    from app.core.cache import get_stats
    return {"redis": redis_health(), "stats": get_stats()}
