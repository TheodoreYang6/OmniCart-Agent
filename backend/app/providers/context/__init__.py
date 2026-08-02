"""内置上下文 Provider 清单 + ContextManager 单例。

对齐 amap ``commons/context_providers`` 的 ``builtin()`` 装配。ContextManager 提供
多源并行采集 + token 预算裁剪，供上下文注入链路复用。
"""

from __future__ import annotations

from app.framework.context import ContextManager, ContextProvider
from app.providers.context.context_providers import (
    FollowUpContextProvider,
    ProfileHintContextProvider,
    TimeContextProvider,
    VisualContextProvider,
)

__all__ = [
    "TimeContextProvider",
    "FollowUpContextProvider",
    "VisualContextProvider",
    "ProfileHintContextProvider",
    "builtin",
    "get_context_manager",
]

# 上下文块 token 预算（注入 prompt 的上下文段落上限，防止长对话撑爆）。
_CONTEXT_TOKEN_BUDGET = 1200


def builtin() -> list[ContextProvider]:
    """返回全部内置上下文 Provider（按 priority 升序）。"""
    return [
        TimeContextProvider(),
        VisualContextProvider(),
        FollowUpContextProvider(),
        ProfileHintContextProvider(),
    ]


_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """进程级 ContextManager 单例（带 token 预算）。"""
    global _manager
    if _manager is None:
        _manager = ContextManager.default(
            builtin=builtin,
            token_budget=_CONTEXT_TOKEN_BUDGET,
            time_budget_ms=2000,
        )
    return _manager
