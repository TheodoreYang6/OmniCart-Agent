import os
from dotenv import load_dotenv

# 确保 .env 在读取配置前加载（无论是直接运行还是被导入）
load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ---- 服务 ----
SERVICE_NAME: str = _env("OMNICART_SERVICE_NAME", "omnicart-agent")
SERVICE_VERSION: str = _env("OMNICART_VERSION", "0.1.0")
HOST: str = _env("OMNICART_HOST", "127.0.0.1")
PORT: int = int(_env("OMNICART_PORT", "8006"))

# ---- Qwen API 密钥（模型名在 model_gateway/model_config.yaml 中管理）----
QWEN_API_KEY: str = _env("QWEN_API_KEY", "")
QWEN_BASE_URL: str = _env("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")

# ---- 检索 ----
DEFAULT_TOP_K: int = int(_env("OMNICART_DEFAULT_TOP_K", "10"))

# ---- Mock Mode ----
MOCK_MODE: bool = _env("OMNICART_MOCK_MODE", "true").lower() == "true"
DEMO_DATA_DIR: str = _env("OMNICART_DEMO_DATA_DIR", "data")

# ---- PostgreSQL ----
DATABASE_URL: str = _env("DATABASE_URL", "")
USE_POSTGRES: bool = bool(DATABASE_URL)

# ---- Qdrant ----
QDRANT_URL: str = _env("QDRANT_URL", "")
QDRANT_COLLECTION_NAME: str = _env("QDRANT_COLLECTION_NAME", "products")
EMBEDDING_DIMENSION: int = int(_env("EMBEDDING_DIMENSION", "1024"))
USE_QDRANT: bool = bool(QDRANT_URL)

# ---- Redis ----
REDIS_URL: str = _env("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL_VISUAL: int = int(_env("REDIS_CACHE_TTL_VISUAL", "3600"))
REDIS_CACHE_TTL_SEARCH: int = int(_env("REDIS_CACHE_TTL_SEARCH", "300"))
REDIS_CACHE_TTL_REWRITE: int = int(_env("REDIS_CACHE_TTL_REWRITE", "1800"))
REDIS_CACHE_TTL_WORKFLOW: int = int(_env("REDIS_CACHE_TTL_WORKFLOW", "300"))
USE_REDIS: bool = _env("REDIS_URL", "").strip() != ""
