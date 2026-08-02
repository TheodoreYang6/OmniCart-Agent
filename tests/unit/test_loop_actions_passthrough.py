"""Loop 分支 actions 透传契约（spec: 混合检索与四bug根治 §4）。

bug：ShopAction 分支透传 res.actions，但深度思考 Loop 分支的 result payload
无 actions 字段 → 多规格商品加购时规格选择按钮消失，用户只能纯对话选。
本测锁住 tool_result 事件必须携带 actions（SSE 层据此汇总进 result）。
"""

import pytest

from app.api.agent_stream import _order_by_cited


class _Res:
    def __init__(self, ok=True, message="", actions=None, data=None):
        self.ok = ok
        self.message = message
        self.actions = actions
        self.data = data or {}


def test_order_by_cited_puts_answer_products_first():
    """回答引用集置顶：products 前 N 必须是回答讲过的商品（spec §3）。"""
    products = [
        {"product_id": "c", "title": "C"},
        {"product_id": "a", "title": "A"},
        {"product_id": "b", "title": "B"},
    ]
    out = _order_by_cited(products, ["a", "b"])
    assert [p["product_id"] for p in out] == ["a", "b", "c"]
    assert out[2].get("beyond_answer") is True
    assert "beyond_answer" not in out[0]


def test_order_by_cited_ignores_unknown_pids():
    products = [{"product_id": "a"}, {"product_id": "b"}]
    out = _order_by_cited(products, ["zzz", "b"])
    assert [p["product_id"] for p in out] == ["b", "a"]


def test_order_by_cited_no_cited_returns_original():
    products = [{"product_id": "a"}, {"product_id": "b"}]
    assert _order_by_cited(products, []) is products
    assert _order_by_cited([], ["a"]) == []


def test_order_by_cited_does_not_mutate_input():
    products = [{"product_id": "a"}, {"product_id": "b"}]
    _order_by_cited(products, ["a"])
    assert "beyond_answer" not in products[1], "不得污染原始 state 数据"


@pytest.mark.asyncio
async def test_loop_tool_result_event_carries_actions(monkeypatch):
    """OmniAgent 的 tool_result 事件必须带 actions（Loop 分支恢复规格按钮的前提）。"""
    from app.agents.omni_agent import OmniAgent
    from app.framework.tools import Tool, ToolContext, ToolRegistry, ToolResult, ToolSpec
    from app.schemas.workflow import WorkflowState

    sku_actions = [
        {"type": "sku_option", "label": "30ml 经典装", "sku_id": "sku-1", "product_id": "p1"},
        {"type": "sku_option", "label": "50ml 加大装", "sku_id": "sku-2", "product_id": "p1"},
    ]

    class _AddCartTool(Tool):
        spec = ToolSpec(name="cart.add", category="cart", description="加购")

        async def run(self, ctx, **kw):
            return ToolResult(message="该商品有多个规格，请选择",
                              data={"needs_sku": True}, actions=sku_actions)

    reg = ToolRegistry(kind="tool")
    reg.register(_AddCartTool())

    class _Gw:
        def __init__(self):
            self.n = 0

        async def chat_with_tools(self, *a, **kw):
            self.n += 1
            if self.n == 1:
                return {"content": "", "tool_calls": [
                    {"id": "1", "name": "cart.add", "arguments": {"product_id": "p1"}}]}
            return {"content": "已为你列出规格供选择", "tool_calls": []}

        async def chat_stream(self, *a, **kw):
            yield "收口"

    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: _Gw())
    monkeypatch.setattr("app.providers.tools.get_tool_registry", lambda: reg)

    ctx = ToolContext(user_id="u1", state=WorkflowState(user_id="u1", user_query="加购这个"))
    events = [ev async for ev in OmniAgent().run_events("加购这个", ctx, True)]
    tool_events = [e for e in events if e.get("type") == "tool_result"]
    assert tool_events, f"未产出 tool_result 事件: {[e.get('type') for e in events]}"
    assert tool_events[0].get("actions") == sku_actions, tool_events[0]
