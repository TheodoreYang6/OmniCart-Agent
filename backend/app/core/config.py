"""OmniCart 配置中心 — pydantic-settings 分组配置 + 向后兼容扁平常量。

设计（借鉴 amap-ai-agent 的强类型配置治理，剔除其内网 Diamond 配置中心）:

- ``Settings(BaseSettings)``：单一可校验配置源。字段按业务域分组（Service /
  Qwen / Mode / Retrieval / Decision / PostgreSQL / Qdrant / Redis-Cache），
  每个字段用 ``validation_alias`` 绑定既有环境变量名，保证零破坏迁移。
- 派生开关：``use_postgres`` / ``use_qdrant`` / ``use_redis`` 用 computed_field
  从连接串是否配置推导，集中一处。
- 向后兼容：模块底部 re-export 全部历史扁平常量（``SERVICE_NAME`` / ``MOCK_MODE``
  / ``USE_QDRANT`` ...），存量 ``from app.core.config import MOCK_MODE`` 无需改动。
- 新代码推荐：``from app.core.config import settings``，再按分组访问
  ``settings.qwen_api_key`` / ``settings.redis_cache_ttl_search`` 等。
"""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仍需把 .env 注入 os.environ：model_gateway/model_config.yaml 用 ${ENV} 占位符做
# 变量替换、qdrant_client 读 NO_PROXY，都直接依赖 os.environ，而 pydantic-settings
# 的 env_file 只填充 Settings 实例、不写回 os.environ。
load_dotenv()


class Settings(BaseSettings):
    """全量应用配置。字段分组见下方注释区块。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 服务 ----
    service_name: str = Field("omnicart-agent", validation_alias="OMNICART_SERVICE_NAME")
    service_version: str = Field("2.0.0", validation_alias="OMNICART_VERSION")
    host: str = Field("127.0.0.1", validation_alias="OMNICART_HOST")
    port: int = Field(8006, validation_alias="OMNICART_PORT")

    # ---- Web 身份与跨域 ----
    session_secret: str = Field(
        "omnicart-development-secret-change-me",
        validation_alias="OMNICART_SESSION_SECRET",
    )
    guest_ttl_days: int = Field(30, validation_alias="OMNICART_GUEST_TTL_DAYS")
    session_cookie_secure: bool = Field(False, validation_alias="OMNICART_SESSION_COOKIE_SECURE")
    cors_origins: str = Field(
        "http://127.0.0.1:5173,http://localhost:5173",
        validation_alias="OMNICART_CORS_ORIGINS",
    )
    allow_legacy_user_id: bool = Field(False, validation_alias="OMNICART_ALLOW_LEGACY_USER_ID")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ---- Qwen API（模型名在 model_gateway/model_config.yaml 管理）----
    qwen_api_key: str = Field("", validation_alias="QWEN_API_KEY")
    qwen_base_url: str = Field("https://dashscope.aliyuncs.com/api/v1", validation_alias="QWEN_BASE_URL")
    asr_model: str = Field("qwen3-asr-flash", validation_alias="OMNICART_ASR_MODEL")
    asr_timeout: float = Field(30.0, validation_alias="OMNICART_ASR_TIMEOUT")

    # ---- DeepSeek API（OpenAI 兼容；文本类能力备选提供商，deepseek* 模型名自动路由）----
    deepseek_api_key: str = Field("", validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field("https://api.deepseek.com/v1", validation_alias="DEEPSEEK_BASE_URL")

    # ---- 模式开关 ----
    mock_mode: bool = Field(True, validation_alias="OMNICART_MOCK_MODE")
    fast_mode: bool = Field(False, validation_alias="OMNICART_FAST_MODE")
    enable_tool_router: bool = Field(True, validation_alias="OMNICART_ENABLE_TOOL_ROUTER")
    # 混合检索（dense + BM25 稀疏向量，服务端 RRF）——**默认关**。
    # 评测证伪（data/rag_eval_runs/purity-*.json 四组对照）：
    #   dense+块权重 0.82 > dense 0.80 > hybrid+块权重 0.78 > hybrid 等权 RRF 0.77
    # 中文短 query 的 sparse 维度极少（"面膜"仅 1 维），RRF 等权下弱信号反而污染前列；
    # 真正的串味根因是 FAQ 块污染（已由块权重修正根治）。保留开关供未来长 query
    # 场景与 SPLADE 升级时重评；开启需集合为 V7 双向量形态。
    enable_hybrid_retrieval: bool = Field(False, validation_alias="OMNICART_ENABLE_HYBRID_RETRIEVAL")
    # P2-3 工具 schema 覆盖表（JSON 文件路径，空=不启用）：只改 LLM 可见描述，不改执行校验
    tool_schema_overrides_path: str = Field("", validation_alias="OMNICART_TOOL_SCHEMA_OVERRIDES")
    # P2-2 转正：三 flag 已过 9 场景统一灰度验证（动态编排基线/compare修复/LLM Planner/
    # 工具链回归全通过，见工作日志），默认开启；可用环境变量关回。
    enable_llm_tool_calling: bool = Field(True, validation_alias="OMNICART_ENABLE_LLM_TOOL_CALLING")
    enable_dynamic_orchestration: bool = Field(True, validation_alias="OMNICART_ENABLE_DYNAMIC_ORCHESTRATION")
    enable_llm_planner: bool = Field(True, validation_alias="OMNICART_ENABLE_LLM_PLANNER")
    # AGENT_LOOP 语义变更（spec: docs/specs/omni-harness）：从"路径开关"降为"能力开关"，
    # 默认 true；仅 deep_think=true 的请求进入 ReAct Loop（深度思考模式），
    # 默认链路仍为 pipeline。关闭可整体禁用深度思考能力。
    enable_agent_loop: bool = Field(True, validation_alias="OMNICART_ENABLE_AGENT_LOOP")
    # 常规推荐只允许一次检索/核对后的收敛机会；深度思考保留有限的多步核验。
    # ``workflow.react.nodes.guard`` 还会施加不可绕过的硬上限，避免环境变量被误配
    # 成长循环而拖慢整条 SSE 链路。
    agent_loop_max_rounds: int = Field(2, validation_alias="OMNICART_AGENT_LOOP_MAX_ROUNDS")
    agent_loop_deep_rounds: int = Field(5, validation_alias="OMNICART_AGENT_LOOP_DEEP_ROUNDS")
    reflect_max_retries: int = Field(1, validation_alias="OMNICART_REFLECT_MAX_RETRIES")
    demo_data_dir: str = Field("data", validation_alias="OMNICART_DEMO_DATA_DIR")

    # ---- 本地模型（embedding / reranker 走本地权重；chat / vision 无本地模型仍走 API）----
    # use_local_models=True 且 mock_mode=False 时，Model Gateway 选用 LocalModelProvider。
    use_local_models: bool = Field(False, validation_alias="OMNICART_USE_LOCAL_MODELS")
    # 本地模型权重根目录（其下含 Qwen3-Embedding-0.6B / Qwen3-Reranker-0.6B 子目录）。
    models_dir: str = Field("", validation_alias="OMNICART_MODELS_DIR")

    # ---- 检索 ----
    default_top_k: int = Field(10, validation_alias="OMNICART_DEFAULT_TOP_K")

    # ---- Decision Agent：证据评分 ----
    enable_decision_llm: bool = Field(False, validation_alias="OMNICART_ENABLE_DECISION_LLM")
    decision_llm_timeout: float = Field(3.0, validation_alias="OMNICART_DECISION_LLM_TIMEOUT")
    # 最终自然语言回答允许短暂的云端波动，避免 6 秒即退回模板。
    # 仍可通过环境变量按部署 SLA 调低；异常、空回答和 Guard 失败照常降级。
    response_llm_timeout: float = Field(15.0, validation_alias="OMNICART_RESPONSE_LLM_TIMEOUT")
    enable_evidence_scoring: bool = Field(True, validation_alias="OMNICART_ENABLE_EVIDENCE_SCORING")
    score_version: str = Field("evidence_scoring_v1", validation_alias="OMNICART_SCORE_VERSION")

    # ---- PostgreSQL ----
    database_url: str = Field("", validation_alias="DATABASE_URL")

    # ---- Qdrant ----
    qdrant_url: str = Field("", validation_alias="QDRANT_URL")
    qdrant_collection_name: str = Field("products", validation_alias="QDRANT_COLLECTION_NAME")
    embedding_dimension: int = Field(1024, validation_alias="EMBEDDING_DIMENSION")
    # V8 separates candidate discovery from evidence.  The legacy chunk index stays
    # configured for rollback until v8 passes the shadow evaluation gate.
    discovery_collection_name: str = Field("product_discovery_v8", validation_alias="OMNICART_DISCOVERY_COLLECTION")
    evidence_collection_name: str = Field("product_evidence_v8", validation_alias="OMNICART_EVIDENCE_COLLECTION")
    use_discovery_v8: bool = Field(False, validation_alias="OMNICART_USE_DISCOVERY_V8")
    # V9：工具调用级的多视角商品 Chunk 检索。当前本地集合已完成真实构建和冒烟验证，
    # 默认启用；环境变量设为 false 可立即回退 V6/V8。
    v9_chunk_collection_name: str = Field("product_chunks_v9", validation_alias="OMNICART_V9_CHUNK_COLLECTION")
    use_v9_chunk_retrieval: bool = Field(True, validation_alias="OMNICART_USE_V9_CHUNK_RETRIEVAL")
    enable_v9_llm_filter: bool = Field(True, validation_alias="OMNICART_ENABLE_V9_LLM_FILTER")
    v9_rerank_timeout: float = Field(4.0, validation_alias="OMNICART_V9_RERANK_TIMEOUT")
    v9_filter_timeout: float = Field(8.0, validation_alias="OMNICART_V9_FILTER_TIMEOUT")
    use_chunked_index: bool = Field(False, validation_alias="OMNICART_USE_CHUNKED_INDEX")
    chunked_collection_name: str = Field("product_chunks", validation_alias="OMNICART_CHUNKED_COLLECTION")

    # ---- 统一 chunk 单集合（V5 架构：版本化命名，重建不覆盖旧集合）----
    chunk_collection_name: str = Field("product_chunks_v6_1024", validation_alias="OMNICART_CHUNK_COLLECTION")
    enable_hybrid: bool = Field(True, validation_alias="OMNICART_ENABLE_HYBRID")
    enable_rerank: bool = Field(True, validation_alias="OMNICART_ENABLE_RERANK")

    # ---- Redis / 四级缓存 ----
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")
    redis_cache_ttl_visual: int = Field(3600, validation_alias="REDIS_CACHE_TTL_VISUAL")
    redis_cache_ttl_search: int = Field(300, validation_alias="REDIS_CACHE_TTL_SEARCH")
    redis_cache_ttl_rewrite: int = Field(1800, validation_alias="REDIS_CACHE_TTL_REWRITE")
    redis_cache_ttl_workflow: int = Field(300, validation_alias="REDIS_CACHE_TTL_WORKFLOW")

    # ---- 派生开关（连接串是否配置 → 是否启用该后端）----
    @computed_field  # type: ignore[prop-decorator]
    @property
    def use_postgres(self) -> bool:
        return bool(self.database_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def use_qdrant(self) -> bool:
        return bool(self.qdrant_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def use_redis(self) -> bool:
        return bool(self.redis_url.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级单例。首次调用完成解析与校验，后续复用。"""
    return Settings()


settings = get_settings()


# ============================================================
# 向后兼容层 — 历史扁平常量 re-export（存量 import 零改动）
# 新代码请优先使用 `settings.<field>`。
# ============================================================

# 服务
SERVICE_NAME: str = settings.service_name
SERVICE_VERSION: str = settings.service_version
HOST: str = settings.host
PORT: int = settings.port

# Qwen
QWEN_API_KEY: str = settings.qwen_api_key
QWEN_BASE_URL: str = settings.qwen_base_url

# DeepSeek
DEEPSEEK_API_KEY: str = settings.deepseek_api_key
DEEPSEEK_BASE_URL: str = settings.deepseek_base_url

# 检索
DEFAULT_TOP_K: int = settings.default_top_k

# 模式
MOCK_MODE: bool = settings.mock_mode
DEMO_DATA_DIR: str = settings.demo_data_dir
USE_LOCAL_MODELS: bool = settings.use_local_models
MODELS_DIR: str = settings.models_dir
FAST_MODE: bool = settings.fast_mode
ENABLE_TOOL_ROUTER: bool = settings.enable_tool_router
TOOL_SCHEMA_OVERRIDES_PATH: str = settings.tool_schema_overrides_path
ENABLE_HYBRID_RETRIEVAL: bool = settings.enable_hybrid_retrieval
ENABLE_LLM_TOOL_CALLING: bool = settings.enable_llm_tool_calling
ENABLE_DYNAMIC_ORCHESTRATION: bool = settings.enable_dynamic_orchestration
ENABLE_LLM_PLANNER: bool = settings.enable_llm_planner
ENABLE_AGENT_LOOP: bool = settings.enable_agent_loop
AGENT_LOOP_MAX_ROUNDS: int = settings.agent_loop_max_rounds
AGENT_LOOP_DEEP_ROUNDS: int = settings.agent_loop_deep_rounds
REFLECT_MAX_RETRIES: int = settings.reflect_max_retries

# PostgreSQL
DATABASE_URL: str = settings.database_url
USE_POSTGRES: bool = settings.use_postgres

# Qdrant
QDRANT_URL: str = settings.qdrant_url
QDRANT_COLLECTION_NAME: str = settings.qdrant_collection_name
EMBEDDING_DIMENSION: int = settings.embedding_dimension
USE_QDRANT: bool = settings.use_qdrant

# Chunked Index
USE_CHUNKED_INDEX: bool = settings.use_chunked_index
CHUNKED_COLLECTION_NAME: str = settings.chunked_collection_name

# 统一 chunk 单集合 + 混合检索开关 (V5)
CHUNK_COLLECTION_NAME: str = settings.chunk_collection_name
DISCOVERY_COLLECTION_NAME: str = settings.discovery_collection_name
EVIDENCE_COLLECTION_NAME: str = settings.evidence_collection_name
USE_DISCOVERY_V8: bool = settings.use_discovery_v8
V9_CHUNK_COLLECTION_NAME: str = settings.v9_chunk_collection_name
USE_V9_CHUNK_RETRIEVAL: bool = settings.use_v9_chunk_retrieval
ENABLE_V9_LLM_FILTER: bool = settings.enable_v9_llm_filter
V9_RERANK_TIMEOUT: float = settings.v9_rerank_timeout
V9_FILTER_TIMEOUT: float = settings.v9_filter_timeout
ENABLE_HYBRID: bool = settings.enable_hybrid
ENABLE_RERANK: bool = settings.enable_rerank

# Decision
ENABLE_DECISION_LLM: bool = settings.enable_decision_llm
DECISION_LLM_TIMEOUT: float = settings.decision_llm_timeout
RESPONSE_LLM_TIMEOUT: float = settings.response_llm_timeout
ENABLE_EVIDENCE_SCORING: bool = settings.enable_evidence_scoring
SCORE_VERSION: str = settings.score_version

# Redis / Cache
REDIS_URL: str = settings.redis_url
REDIS_CACHE_TTL_VISUAL: int = settings.redis_cache_ttl_visual
REDIS_CACHE_TTL_SEARCH: int = settings.redis_cache_ttl_search
REDIS_CACHE_TTL_REWRITE: int = settings.redis_cache_ttl_rewrite
REDIS_CACHE_TTL_WORKFLOW: int = settings.redis_cache_ttl_workflow
USE_REDIS: bool = settings.use_redis
