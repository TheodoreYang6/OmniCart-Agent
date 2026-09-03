"""会话工具族（conversation.*）—— 对话历史查看与上下文重置（Phase 6-B3）。

纯工具：直接消费 ConversationService；conversation_id 来自 ToolContext。
"""

from __future__ import annotations

import logging

from app.framework.tools import Tool, ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

__all__ = ["ConversationHistoryTool", "ConversationResetTool"]


def _conv_svc():
    from app.services.conversation_service import get_conversation_service

    return get_conversation_service()


class ConversationHistoryTool(Tool):
    spec = ToolSpec(
        name="conversation.history",
        category="conversation",
        permission="read",
        description="回顾当前会话最近聊过的内容",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 6, "description": "最近几条"}},
        },
    )

    async def run(self, ctx: ToolContext, limit: int = 6) -> ToolResult:
        if not ctx.conversation_id:
            return ToolResult(message="我们才刚开始聊哦～有什么想买的直接说！")
        try:
            msgs = _conv_svc().get_messages(ctx.conversation_id, limit=max(1, min(20, limit)))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"conversation.history failed: {e}")
            return ToolResult(ok=False, message="暂时想不起来聊了什么，请稍后再试～")
        msgs = [m for m in msgs if (m.get("content") or "").strip()]
        if not msgs:
            return ToolResult(message="我们才刚开始聊哦～有什么想买的直接说！")
        lines = ["📝 最近聊过："]
        for m in msgs[-limit:]:
            who = "你" if m.get("role") == "user" else "欧米"
            lines.append(f"  {who}: {(m.get('content') or '')[:40]}")
        return ToolResult(message="\n".join(lines), data={"count": len(msgs)})


class ConversationResetTool(Tool):
    spec = ToolSpec(
        name="conversation.reset",
        category="conversation",
        permission="write",
        description="清空当前会话上下文（聚焦商品/待选规格/待确认订单/上一轮推荐），重新开始",
        parameters={"type": "object", "properties": {}},
    )

    async def run(self, ctx: ToolContext) -> ToolResult:
        if not ctx.conversation_id:
            return ToolResult(message="好的～我们重新开始，想看点什么？")
        try:
            await _conv_svc().aupdate_context_snapshot(
                ctx.conversation_id,
                {
                    "focus_product": None,
                    "pending_sku_product": None,
                    "pending_order_items": None,
                    "last_products": [],
                    "last_orders": [],
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"conversation.reset failed: {e}")
            return ToolResult(ok=False, message="重置失败，请稍后再试～")
        return ToolResult(message="✅ 好的，上下文已清空，我们重新开始～想看点什么？")
