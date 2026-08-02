"""短期 / 会话记忆 Provider —— 把三层记忆的另两层接入统一 MemoryBank。

- :class:`ShortTermMemoryProvider`：从 ``conversation.context_snapshot`` 读取累积约束、
  聚焦商品，产出短期记忆项。
- :class:`ConversationHistoryProvider`：读取最近若干轮消息，产出会话记忆项。

二者均通过 ``request.metadata["conversation_id"]`` 定位会话，使用 ConversationService 的
**异步**接口（避免在事件循环内触发同步桥接）。无 conversation_id 时不激活。
"""

from __future__ import annotations

import logging

from app.framework.memory import MemoryItem, MemoryProvider, MemoryRecallRequest, MemoryRecallResult
from app.framework.registry import component

logger = logging.getLogger(__name__)


def _conversation_id(request: MemoryRecallRequest) -> str:
    return str(request.metadata.get("conversation_id", "") or "")


@component(kind="memory_provider", name="short_term", priority=20)
class ShortTermMemoryProvider(MemoryProvider):
    """短期上下文记忆（context_snapshot 的约束/聚焦商品）。"""

    name = "short_term"
    priority = 20

    def should_activate(self, request: MemoryRecallRequest) -> bool:
        return bool(_conversation_id(request))

    async def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        from app.services.conversation_service import get_conversation_service

        cid = _conversation_id(request)
        snapshot = await get_conversation_service().get_context_snapshot(cid)
        items: list[MemoryItem] = []

        constraints = snapshot.get("constraints", {}) or {}
        parts = [f"{k}={v}" for k, v in constraints.items() if v]
        if parts:
            items.append(
                MemoryItem(
                    memory_id=f"ST-{cid}-constraints",
                    text="当前约束: " + ", ".join(parts),
                    score=1.0,
                    memory_type="short_term",
                    extra={"constraints": constraints},
                )
            )
        focus = snapshot.get("focus_product") or {}
        if focus.get("product_id"):
            items.append(
                MemoryItem(
                    memory_id=f"ST-{cid}-focus",
                    text=f"聚焦商品: {focus.get('brand', '')} {focus.get('title', '')}",
                    score=0.9,
                    memory_type="short_term",
                    extra={"focus_product": focus},
                )
            )
        return MemoryRecallResult(self.name, items=items)


@component(kind="memory_provider", name="conversation_history", priority=30)
class ConversationHistoryProvider(MemoryProvider):
    """会话历史记忆（最近若干轮消息）。"""

    name = "conversation_history"
    priority = 30

    def __init__(self, *, limit: int = 6) -> None:
        self._limit = limit

    def should_activate(self, request: MemoryRecallRequest) -> bool:
        return bool(_conversation_id(request))

    async def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        from app.services.conversation_service import get_conversation_service

        cid = _conversation_id(request)
        ctx = await get_conversation_service().aget_context(cid, limit=self._limit)
        messages = ctx.get("recent_messages", []) or []
        items: list[MemoryItem] = []
        total = len(messages)
        for i, msg in enumerate(messages):
            items.append(
                MemoryItem(
                    memory_id=f"CH-{cid}-{i}",
                    text=f"[{msg.get('role', '')}] {str(msg.get('content', ''))[:200]}",
                    score=(i + 1) / total if total else 0.0,  # 越近的消息分越高
                    memory_type="conversation",
                    extra={"role": msg.get("role", "")},
                )
            )
        return MemoryRecallResult(self.name, items=items)
