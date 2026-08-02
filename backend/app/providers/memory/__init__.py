"""内置记忆 Provider 清单 + MemoryBank 单例（对齐 amap ``commons/memory_providers``）。

三层记忆统一到一个 MemoryBank：偏好(preference) / 短期(short_term) / 会话(conversation_history)。
调用方按需用 ``include={...}`` 选择要跑的 Provider。
"""

from __future__ import annotations

from app.framework.memory import MemoryBank, MemoryProvider
from app.providers.memory.preference_provider import (
    PreferenceMemoryProvider,
    PreferenceWriter,
)
from app.providers.memory.session_providers import (
    ConversationHistoryProvider,
    ShortTermMemoryProvider,
)

__all__ = [
    "PreferenceMemoryProvider",
    "PreferenceWriter",
    "ShortTermMemoryProvider",
    "ConversationHistoryProvider",
    "builtin",
    "get_memory_bank",
    "get_preference_writer",
    "recall_used_memories",
]


def builtin() -> list[MemoryProvider]:
    """返回全部内置记忆 Provider 实例（按 priority 升序）。"""
    return [
        PreferenceMemoryProvider(),
        ShortTermMemoryProvider(),
        ConversationHistoryProvider(),
    ]


_bank: MemoryBank | None = None
_writer: PreferenceWriter | None = None


def get_memory_bank() -> MemoryBank:
    """进程级 MemoryBank 单例。"""
    global _bank
    if _bank is None:
        _bank = MemoryBank.default(builtin_providers=builtin())
    return _bank


def get_preference_writer() -> PreferenceWriter:
    global _writer
    if _writer is None:
        _writer = PreferenceWriter()
    return _writer


# 放在末尾导入：used_memories 依赖上面的 get_memory_bank（避免包内循环导入）。
from app.providers.memory.used_memories import recall_used_memories  # noqa: E402
