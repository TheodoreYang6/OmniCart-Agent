"""ToolDispatcher —— 双路调度。

① RuleToolRouter：关键词 → (tool_name, args)，0 LLM 延迟、MOCK 安全（Phase 1 仅纯购物车）。
② LLM 函数调用（Phase 6-B1）：OpenAI tools 协议，LLM 从白名单工具中选择并填参；
   ``ENABLE_LLM_TOOL_CALLING`` 关 / MOCK 惰性 / 异常 → 降级。
两路都未命中 → 返回 ``error="no_match"``，由调用方交回旧逻辑。
"""

from __future__ import annotations

import logging

from app.framework.tools.ordinal import OrdinalResolver
from app.framework.tools.protocols import ToolContext, ToolResult
from app.framework.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

__all__ = ["RuleToolRouter", "ToolDispatcher"]

# Phase 1 纯购物车关键词（取自 agent_stream 词表，保持一致的检测顺序）
_CART_SHOW = ["购物车有什么", "看看购物车", "看购物车"]
_CART_REMOVE = ["删除第", "去掉第", "移除第"]
_CART_QTY = ["数量改成", "数量改为", "数量改成第", "数量改为第"]
_CART_CLEAR = ["清空购物车"]

# LLM 工具选择器 system prompt：只在明确匹配时选工具，否则不选（降级回兜底/推荐流）
_TOOL_SELECT_SYSTEM = (
    "你是电商购物助手的工具调度器。根据用户消息判断是否需要调用某个工具：\n"
    "- 仅当用户意图与某工具功能明确匹配时才选择该工具，并从消息中提取参数；\n"
    "- 意图模糊、闲聊、或属于商品推荐咨询时，不要选择任何工具；\n"
    "- 最多选择一个工具。"
)


class RuleToolRouter:
    """关键词 → (tool_name, args)。未命中返回 (None, None)。"""

    def match(self, msg: str, ctx: ToolContext) -> tuple[str | None, dict | None]:
        if any(kw in msg for kw in _CART_SHOW):
            return "cart.view", {}
        if any(kw in msg for kw in _CART_REMOVE):
            n = OrdinalResolver.parse_ordinal(msg, r"删除第|去掉第|移除第")
            return "cart.remove", {"ordinal": n}
        if any(kw in msg for kw in _CART_QTY):
            qty = OrdinalResolver.parse_qty(msg)
            n = OrdinalResolver.parse_ordinal(msg, r"第")
            return "cart.update_qty", {"quantity": qty, "ordinal": n}
        if any(kw in msg for kw in _CART_CLEAR):
            return "cart.clear", {}
        return None, None


class ToolDispatcher:
    """先规则路由；未命中再（可选）LLM 函数调用；仍无 → error=no_match 交回旧逻辑。"""

    def __init__(self, registry: ToolRegistry):
        self._registry = registry
        self._router = RuleToolRouter()

    async def dispatch(self, msg: str, ctx: ToolContext) -> ToolResult:
        name, args = self._router.match(msg, ctx)
        if name:
            return await self._registry.invoke(name, args or {}, ctx)

        # LLM 函数调用路径（Phase 6-B1）：flag 关 / MOCK 惰性 / 异常 → 降级 no_match
        from app.core.config import ENABLE_LLM_TOOL_CALLING

        if ENABLE_LLM_TOOL_CALLING:
            try:
                from app.model_gateway.gateway import get_model_gateway

                schemas = self._registry.openai_schemas(llm_only=True)
                if schemas:
                    choice = await get_model_gateway().chat_with_tools(
                        "tool_calling",
                        [{"role": "user", "content": msg}],
                        schemas,
                        system=_TOOL_SELECT_SYSTEM,
                    )
                    calls = (choice or {}).get("tool_calls") or []
                    if calls:
                        tc = calls[0]
                        tool_name = tc.get("name", "")
                        if self._registry.get_optional(tool_name) is not None:
                            logger.info(f"LLM tool-calling selected: {tool_name}({tc.get('args')})")
                            return await self._registry.invoke(tool_name, tc.get("args", {}) or {}, ctx)
                        logger.warning(f"LLM selected unknown tool: {tool_name!r}")
            except Exception as e:  # noqa: BLE001 — 工具选择失败降级，不阻断主链
                logger.debug(f"LLM tool-calling skipped: {e}")

        return ToolResult(ok=False, error="no_match")
