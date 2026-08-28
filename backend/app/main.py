import logging
import time
from uuid import uuid4
from contextlib import asynccontextmanager
from pathlib import Path

# 确保 prompt 日志可见
logging.getLogger("omnicart.prompt").setLevel(logging.INFO)

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
from app.api.agent_stream import router as agent_stream_router
from app.api.conversation import router as conversation_router
from app.api.user_profile import router as user_profile_router
from app.core.config import SERVICE_NAME, SERVICE_VERSION, DEMO_DATA_DIR, USE_POSTGRES, USE_QDRANT, USE_REDIS, settings

logger = logging.getLogger(__name__)

app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_trace(request, call_next):
    """Attach a stable request id and emit a concise, privacy-safe HTTP trace.

    SSE has its own event-level trace in ``agent_stream``; this middleware makes
    ordinary cart/auth/upload failures equally diagnosable without logging query
    text, images, audio, tokens, or cookies.
    """
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_error request_id=%s method=%s path=%s",
            request_id, request.method, request.url.path,
        )
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "http request_id=%s method=%s path=%s status=%s elapsed_ms=%d client=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request.headers.get("X-Client-Platform", "unknown"),
    )
    return response

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
app.include_router(agent_stream_router)
app.include_router(conversation_router)
app.include_router(user_profile_router)


async def on_startup():
    """启动时初始化数据库连接（如果配置了）。"""
    # Composition root 预装配：工具注册表单例 + 向 framework Planner 注入
    # 工具 schema 来源（P0-2：消除懒装配的时序风险，LLMPlanner 首次使用前必就位）
    from app.providers.tools import get_tool_registry

    get_tool_registry()

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
            logger.warning(f"Qdrant init failed: {e} — falling back to local embedding cache")
    else:
        logger.info("Qdrant not configured — using local embedding cache mode")

    if USE_REDIS:
        try:
            from app.core.redis_client import init_redis
            await init_redis()
        except Exception as e:
            logger.warning(f"Redis init failed: {e} — cache disabled")

    # 本地模型后台预热 — 首请求免受权重加载拖累（~11s）；不阻塞服务就绪
    from app.core.config import USE_LOCAL_MODELS, MOCK_MODE
    if USE_LOCAL_MODELS and not MOCK_MODE:
        import asyncio

        async def _warmup_local_models():
            try:
                from app.model_gateway import local_backend as lb
                # 在线程中加载 + 各跑一次 dummy 推理（embed 与 rerank 两个模型都预热）
                await asyncio.to_thread(lb.embed_texts, ["预热"])
                await asyncio.to_thread(lb.rerank_logits, "预热", ["预热文档"])
                logger.info("Local models warmed up (embedding + reranker)")
            except Exception as e:
                logger.warning(f"Local model warmup skipped: {e}")

        asyncio.create_task(_warmup_local_models())


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Own local infrastructure connections for the whole application lifetime."""
    await on_startup()
    try:
        yield
    finally:
        await on_shutdown()


app.router.lifespan_context = lifespan


@app.get("/")
async def root():
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION}
