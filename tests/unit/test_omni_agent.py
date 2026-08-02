"""Phase 7 OmniAgent ReAct 循环器单测 —— fake gateway 脚本化多轮。"""

import pytest

from app.agents.omni_agent import OmniAgent
from app.framework.tools import Tool, ToolContext, ToolResult, ToolSpec, ToolRegistry
from app.schemas.workflow import WorkflowState


# ---- fakes ----

class _SearchTool(Tool):
    spec = ToolSpec(name="shopping.search", category="shopping", description="搜",
                    parameters={"type": "object", "properties": {"query": {"type": "string"}}})

    async def run(self, ctx, query: str = "", top_k: int = 5, **kw):
        if ctx.state is not None:
            ctx.state.retrieved_products = [
                {"product_id": "P-A", "title": f"{query}旗舰", "brand": "TestBrand", "price": 999}]
        return ToolResult(message=f"「{query}」深度检索到 1 件", data={"products": [{"product_id": "P-A"}]})


class _OrderListTool(Tool):
    spec = ToolSpec(name="order.list", category="order", description="订单")

    async def run(self, ctx, **kw):
        return ToolResult(message="1 单：ORD-X [待支付]")


class _InvTool(Tool):
    spec = ToolSpec(name="shopping.check_inventory", category="shopping", description="库存")

    async def run(self, ctx, **kw):
        return ToolResult(message="有货")


class _ConfirmTool(Tool):
    spec = ToolSpec(name="order.submit2", category="order", permission="order", description="提交")

    async def run(self, ctx, **kw):
        return ToolResult(message="ok")


class _BoomTool(Tool):
    spec = ToolSpec(name="test.boom", category="test", description="炸")

    async def run(self, ctx, **kw):
        raise RuntimeError("boom")


def _registry(*tools) -> ToolRegistry:
    r = ToolRegistry(kind="tool")
    for t in tools:
        r.register(t)
    return r


class _ScriptGw:
    """按调用次序返回脚本化 choice；记录每次收到的 messages。"""

    def __init__(self, script):
        self.script, self.calls, self.seen_messages = list(script), 0, []
        self.stream_calls = 0

    async def chat_with_tools(self, capability, messages, tools, system=""):
        self.seen_messages.append([dict(m) for m in messages])
        self.calls += 1
        if self.calls <= len(self.script):
            return self.script[self.calls - 1]
        return {"content": "结束", "tool_calls": []}

    async def chat_stream(self, capability, prompt, system=""):
        # 收口轮（spec omni-harness D2）：预算最后一轮 chat_stream 真流式产终稿
        self.stream_calls += 1
        for tok in ("收口", "回答"):
            yield tok


def _call(name, args=None, cid="c1"):
    return {"id": cid, "name": name, "args": args or {}}


async def _run(script, tools, deep_think=False, monkeypatch=None):
    gw = _ScriptGw(script)
    reg = _registry(*tools)
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    monkeypatch.setattr("app.providers.tools.get_tool_registry", lambda: reg)
    state = WorkflowState(user_id="u1", user_query="q")
    ctx = ToolContext(user_id="u1", state=state)
    events = []
    async for ev in OmniAgent().run_events("推荐一款蓝牙耳机", ctx, deep_think=deep_think):
        events.append(ev)
    return events, state, gw


# ---- 主流程 ----

async def test_single_search_round_then_conclude(monkeypatch):
    events, state, gw = await _run(
        [{"content": "", "tool_calls": [_call("shopping.search", {"query": "蓝牙耳机"})]},
         {"content": "信息足够了：TestBrand 旗舰最合适", "tool_calls": []}],
        [_SearchTool()], monkeypatch=monkeypatch)
    kinds = [e["type"] for e in events]
    # spec D2：自然结束轮 content 即终稿，多发 answer 事件（SSE 层按块回放）
    assert kinds == ["status", "tool_result", "answer", "done"]
    assert state.retrieved_products and state.retrieved_products[0]["product_id"] == "P-A"
    assert "[欧米的分析结论" in state.context_prompt and "TestBrand" in state.context_prompt
    # 终稿权在 Loop：answer 直接写回 state
    assert state.answer == "信息足够了：TestBrand 旗舰最合适"
    # 第二轮请求里含 role=tool 回填
    assert any(m.get("role") == "tool" for m in gw.seen_messages[1])
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in gw.seen_messages[1])


async def test_multi_calls_one_round_in_order(monkeypatch):
    events, state, gw = await _run(
        [{"content": "", "tool_calls": [_call("order.list", cid="a"),
                                        _call("shopping.check_inventory", cid="b")]},
         {"content": "done", "tool_calls": []}],
        [_OrderListTool(), _InvTool()], monkeypatch=monkeypatch)
    tool_evs = [e for e in events if e["type"] == "tool_result"]
    assert [e["tool"] for e in tool_evs] == ["order.list", "shopping.check_inventory"]
    # skill_executions 由 registry 落 trace
    assert [s["skill_name"] for s in state.skill_executions] == ["order.list", "shopping.check_inventory"]


# ---- 预算与防循环 ----

async def test_budget_normal_three_rounds(monkeypatch):
    script = [{"content": "", "tool_calls": [_call("order.list", {"limit": i})]} for i in range(10)]
    events, state, gw = await _run(script, [_OrderListTool()], monkeypatch=monkeypatch)
    # spec D2 收口轮：max_rounds=3 = 2 轮工具(chat_with_tools) + 1 收口轮(chat_stream)
    assert gw.calls == 2 and gw.stream_calls == 1
    assert events[-1]["type"] == "done" and events[-1]["rounds"] == 3
    # 收口轮真流式 token 事件 + 终稿写回 state
    assert any(e["type"] == "token" for e in events)
    assert state.answer == "收口回答"


async def test_budget_deep_think_eight_rounds(monkeypatch):
    script = [{"content": "", "tool_calls": [_call("order.list", {"limit": i})]} for i in range(20)]
    events, _, gw = await _run(script, [_OrderListTool()], deep_think=True, monkeypatch=monkeypatch)
    assert gw.calls == 7 and gw.stream_calls == 1  # 8 轮预算 = 7 工具轮 + 1 收口轮


async def test_repeated_calls_force_stop(monkeypatch):
    same = {"content": "", "tool_calls": [_call("order.list", {"limit": 5})]}
    events, _, gw = await _run([same, same, same], [_OrderListTool()], monkeypatch=monkeypatch)
    assert gw.calls == 2  # 第二轮识别重复签名强制结束
    assert events[-1]["type"] == "done"


# ---- 异常与确认 ----

async def test_confirmation_required_backfilled(monkeypatch):
    events, _, gw = await _run(
        [{"content": "", "tool_calls": [_call("order.submit2")]},
         {"content": "需要你确认后才能提交哦", "tool_calls": []}],
        [_ConfirmTool()], monkeypatch=monkeypatch)
    # permission=order 未带 _confirmed → registry 拦截 → 回填确认引导文本
    tool_msgs = [m for m in gw.seen_messages[1] if m.get("role") == "tool"]
    assert tool_msgs and "需要用户本人确认" in tool_msgs[0]["content"]
    assert events[-1]["type"] == "done"


async def test_tool_exception_continues(monkeypatch):
    events, _, gw = await _run(
        [{"content": "", "tool_calls": [_call("test.boom")]},
         {"content": "工具失败了，换个方式回答", "tool_calls": []}],
        [_BoomTool()], monkeypatch=monkeypatch)
    tool_msgs = [m for m in gw.seen_messages[1] if m.get("role") == "tool"]
    assert tool_msgs and "[工具失败]" in tool_msgs[0]["content"]
    assert events[-1]["type"] == "done"  # 循环未中断


async def test_gateway_exception_propagates(monkeypatch):
    class _BadGw:
        async def chat_with_tools(self, *a, **kw):
            raise RuntimeError("llm down")

    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: _BadGw())
    monkeypatch.setattr("app.providers.tools.get_tool_registry", lambda: _registry(_OrderListTool()))
    ctx = ToolContext(user_id="u1", state=WorkflowState())
    with pytest.raises(RuntimeError):  # 由入口 try/except 降级到 workflow
        async for _ in OmniAgent().run_events("随便", ctx):
            pass
