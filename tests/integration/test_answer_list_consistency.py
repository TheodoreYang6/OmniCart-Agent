"""§5.2 验收：答文与列表强一致 + Loop 规格按钮（spec 混合检索与四bug根治）。

这两项是用户直报 bug 的验收口：
- bug#3 回答与商品列表不一致 → result.products 前 N 必须是回答引用集（同序）
- bug#4 深度思考下规格按钮消失 → result.actions 必须含 sku_option（带 product_id）
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _last_result(raw: str) -> dict:
    """从 SSE 流中取最后一个 result 帧。"""
    out = {}
    for block in raw.split("\n\n"):
        if "event: result" in block:
            for line in block.splitlines():
                if line.startswith("data: "):
                    out = json.loads(line[6:])
    return out


@pytest.mark.integration
def test_result_products_head_matches_answer_cited_pids():
    """result.products 前 N 个 == 回答引用集（spec §5.2 答文一致门槛）。"""
    client = TestClient(app)
    with client.stream("POST", "/api/recommend/stream", json={
        "user_id": "it_cited", "message": "推荐面膜",
    }) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    d = _last_result(raw)
    products = d.get("products") or []
    if not products:
        pytest.skip("检索无结果（依赖向量库），跳过一致性断言")

    # 未被回答引用的商品必须排在被引用商品之后，且标 beyond_answer
    cited_head = []
    for p in products:
        if p.get("beyond_answer"):
            break
        cited_head.append(p)
    assert cited_head, "products 首位不应是 beyond_answer 商品"
    for p in products[len(cited_head):]:
        assert p.get("beyond_answer") is True, f"引用集之后的商品未标记: {p.get('product_id')}"

    answer = d.get("answer") or ""
    assert answer, "应有回答"
    # 兑底/闲聊模板（测试环境 LLM 不可用时会走到）不参与引用校验——
    # 上面的置顶/beyond_answer 结构契约才是本测要锁的东西
    _FALLBACKS = ("没太看懂", "抑或欧米更擅长", "抱歉，没有找到")
    if any(f in answer for f in _FALLBACKS):
        pytest.skip(f"回答为兑底模板（LLM 不可用），已验结构契约: {answer[:24]}")
    # 回答至少引用 head 中一款（标题前 6 字或品牌）
    hit = any((p.get("title") or "")[:6] in answer for p in cited_head)
    assert hit or any((p.get("brand") or "") in answer for p in cited_head), (
        f"回答未引用置顶商品: {[p.get('title', '')[:12] for p in cited_head]} | {answer[:60]}")


@pytest.mark.integration
def test_deep_think_result_carries_sku_option_actions(monkeypatch):
    """deep_think 加购多规格商品 → result.actions 含带 product_id 的 sku_option。

    不依赖 LLM 自主选工具（实测 LLM 常改走推荐）：直接脚本化工具调用，
    验证 SSE 层 actions 透传契约（bug#4 的根因就在这条链路上）。
    """
    from app.framework.tools import Tool, ToolRegistry, ToolResult, ToolSpec

    sku_actions = [
        {"type": "sku_option", "label": "30ml ¥720", "sku_id": "s1", "product_id": "p_x"},
        {"type": "sku_option", "label": "50ml ¥1080", "sku_id": "s2", "product_id": "p_x"},
    ]

    class _AddTool(Tool):
        spec = ToolSpec(name="cart.add", category="cart", description="加购")

        async def run(self, ctx, **kw):
            return ToolResult(message="该商品有 2 个规格，选哪个？",
                              data={"needs_sku": {"product_id": "p_x"}}, actions=sku_actions)

    reg = ToolRegistry(kind="tool")
    reg.register(_AddTool())

    class _Gw:
        def __init__(self):
            self.n = 0

        async def chat_with_tools(self, *a, **kw):
            self.n += 1
            if self.n == 1:
                return {"content": "", "tool_calls": [
                    {"id": "1", "name": "cart.add", "arguments": {"product_id": "p_x"}}]}
            return {"content": "这款有两个规格，点按钮选一下就好啦～", "tool_calls": []}

        async def chat_stream(self, *a, **kw):
            yield "这款有两个规格，点按钮选一下就好啦～"

        async def chat(self, *a, **kw):
            return "这款有两个规格，点按钮选一下就好啦～"

    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: _Gw())
    monkeypatch.setattr("app.providers.tools.get_tool_registry", lambda: reg)

    client = TestClient(app)
    with client.stream("POST", "/api/recommend/stream", json={
        "user_id": "it_sku", "message": "把这个加入购物车", "deep_think": True,
    }) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    d = _last_result(raw)
    assert d.get("agent_loop") is True, f"未走 Loop 分支: {d.get('agent_loop')}"
    actions = d.get("actions") or []
    assert actions, f"Loop 分支 result 未带 actions（bug#4 回归）: {list(d.keys())}"
    skus = [a for a in actions if a.get("type") == "sku_option"]
    assert len(skus) >= 2, actions
    assert all(a.get("product_id") for a in skus), "sku_option 缺 product_id（前端无法直连加购）"
