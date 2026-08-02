"""Context 框架层（framework.context）—— 借鉴 amap ``libs/context_store`` + ``context_compaction``。

框架-实现分离：本包只含 Protocol/ABC + 编排（ContextManager）+ 分级压缩（TierSelector）+
Token 估算；具体 ContextProvider 实现见 ``app.providers.context``。
"""

from __future__ import annotations

from app.framework.context.compaction import Tier, TierSelector, TierThresholds
from app.framework.context.manager import ContextManager
from app.framework.context.protocols import (
    ContextBundle,
    ContextProvider,
    ContextSlice,
    ContextTrigger,
)
from app.framework.context.token_estimator import (
    CharTokenEstimator,
    TokenEstimator,
    create_token_estimator,
)

__all__ = [
    "ContextProvider",
    "ContextTrigger",
    "ContextSlice",
    "ContextBundle",
    "ContextManager",
    "Tier",
    "TierThresholds",
    "TierSelector",
    "TokenEstimator",
    "CharTokenEstimator",
    "create_token_estimator",
]
