"""RAG 框架层（framework.retrieval）—— 借鉴 amap ``libs/knowledge_base``。

框架-实现分离：本包只含 Protocol/ABC + 编排逻辑；具体召回源实现见
``app.providers.recall``。公开 API 在此统一导出。
"""

from __future__ import annotations

from app.framework.retrieval.errors import RequiredSourceError, RetrievalError
from app.framework.retrieval.fusion import RetrievalFusion, RRFFusion, SequentialFusion
from app.framework.retrieval.orchestrator import RetrievalOrchestrator
from app.framework.retrieval.registry import SourceRegistry
from app.framework.retrieval.rewrite import NoopQueryRewriter, QueryRewriter
from app.framework.retrieval.source import (
    STAGE_ENRICH,
    STAGE_FALLBACK,
    STAGE_RECALL,
    RecallSource,
)
from app.framework.retrieval.types import (
    RetrievalBundle,
    RetrievalQuery,
    RetrievalResult,
)

__all__ = [
    "RecallSource",
    "STAGE_RECALL",
    "STAGE_FALLBACK",
    "STAGE_ENRICH",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalBundle",
    "RetrievalFusion",
    "SequentialFusion",
    "RRFFusion",
    "QueryRewriter",
    "NoopQueryRewriter",
    "SourceRegistry",
    "RetrievalOrchestrator",
    "RetrievalError",
    "RequiredSourceError",
]
