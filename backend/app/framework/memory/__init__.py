"""Memory 框架层（framework.memory）—— 借鉴 amap ``libs/memory_bank``。

框架-实现分离：本包只含 Protocol/ABC + 编排（MemoryBank / RecallEngine / Fusion /
Rerank）；具体 Provider 实现见 ``app.providers.memory``。
"""

from __future__ import annotations

from app.framework.memory.bank import MemoryBank
from app.framework.memory.fusion import RRFFusion, SimpleMergeFusion
from app.framework.memory.paths import RecencyPath, TagPath
from app.framework.memory.protocols import (
    FusionStrategy,
    MemoryItem,
    MemoryProvider,
    MemoryRecallRequest,
    MemoryRecallResult,
    QueryRewriter,
    RerankStrategy,
    RetrievalPath,
)
from app.framework.memory.recall import DefaultRecallEngine
from app.framework.memory.rerank import MMRReranker, NoopReranker

__all__ = [
    "MemoryItem",
    "MemoryRecallRequest",
    "MemoryRecallResult",
    "MemoryProvider",
    "RetrievalPath",
    "FusionStrategy",
    "RerankStrategy",
    "QueryRewriter",
    "RRFFusion",
    "SimpleMergeFusion",
    "MMRReranker",
    "NoopReranker",
    "DefaultRecallEngine",
    "MemoryBank",
    "TagPath",
    "RecencyPath",
]
