from fastapi import APIRouter

from app.core.config import SERVICE_NAME, SERVICE_VERSION

router = APIRouter()


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }
