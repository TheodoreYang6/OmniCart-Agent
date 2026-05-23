import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.recommend import router as recommend_router
from app.api.upload import router as upload_router
from app.api.products import router as products_router
from app.api.cart import router as cart_router
from app.api.checkout import router as checkout_router
from app.api.agent_actions import router as agent_actions_router
from app.api.auth import router as auth_router
from app.api.address import router as address_router
from app.api.preference import router as preference_router
from app.api.observability import router as observability_router
from app.api.voice import router as voice_router
from app.api.eval import router as eval_router
from app.api.eval_dashboard import router as dashboard_router
from app.core.config import SERVICE_NAME, SERVICE_VERSION, DEMO_DATA_DIR, USE_POSTGRES, USE_QDRANT, USE_REDIS

logger = logging.getLogger(__name__)

app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件 — 上传的图片
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / DEMO_DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# 语音文件
VOICE_DIR = UPLOAD_DIR / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads/voice", StaticFiles(directory=str(VOICE_DIR)), name="voice_uploads")

# 静态文件 — 官方数据集图片
DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "ecommerce_agent_dataset"
if DATASET_DIR.is_dir():
    app.mount("/images", StaticFiles(directory=str(DATASET_DIR)), name="dataset_images")

# 路由
app.include_router(health_router)
app.include_router(recommend_router)
app.include_router(upload_router)
app.include_router(products_router)
app.include_router(cart_router)
app.include_router(checkout_router)
app.include_router(agent_actions_router)
app.include_router(auth_router)
app.include_router(address_router)
app.include_router(preference_router)
app.include_router(observability_router)
app.include_router(voice_router)
app.include_router(eval_router)
app.include_router(dashboard_router)


@app.on_event("startup")
async def on_startup():
    """启动时初始化数据库连接（如果配置了）。"""
    if USE_POSTGRES:
        try:
            from app.core.database import init_db
            await init_db()
            logger.info("PostgreSQL connected and tables initialized")
        except Exception as e:
            logger.warning(f"PostgreSQL init failed: {e} — falling back to JSON mode")
    else:
        logger.info("PostgreSQL not configured — using JSON file mode")

    if USE_QDRANT:
        try:
            from app.core.qdrant_client import init_qdrant
            await init_qdrant()
            logger.info("Qdrant connected and collection ready")
        except Exception as e:
            logger.warning(f"Qdrant init failed: {e} — falling back to keyword search")
    else:
        logger.info("Qdrant not configured — using jieba keyword mode")

    if USE_REDIS:
        try:
            from app.core.redis_client import init_redis
            await init_redis()
        except Exception as e:
            logger.warning(f"Redis init failed: {e} — cache disabled")


@app.on_event("shutdown")
async def on_shutdown():
    """关闭时释放数据库连接。"""
    if USE_POSTGRES:
        try:
            from app.core.database import close_db
            await close_db()
            logger.info("PostgreSQL connection closed")
        except Exception:
            pass

    if USE_QDRANT:
        try:
            from app.core.qdrant_client import close_qdrant
            await close_qdrant()
            logger.info("Qdrant connection closed")
        except Exception:
            pass

    if USE_REDIS:
        try:
            from app.core.redis_client import close_redis
            await close_redis()
        except Exception:
            pass


@app.get("/")
async def root():
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION}
