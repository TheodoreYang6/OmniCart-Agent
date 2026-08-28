"""OmniAgent 薄壳单测 —— fake gateway 脚本化多轮。

手写 ReAct 循环已退役，``OmniAgent`` 现在只是 ``app.workflow.react`` 双档同构图的
事件适配层。本文件验的是**对外契约**：事件序列、OpenAI 协议回填、防循环、
预算、确认拦截、工具异常不中断 —— 这些在退役前后都必须成立。

与退役前的一处刻意差异：图内不做逐 token 流式（设计决定“图内不流，SSE 层流”），
所以不再有 ``chat_stream`` 收口轮与 ``token`` 事件；终稿以单个 ``answer`` 事件外显。
图节点层面的行为（只读并行、拓扑同构、闸门）由 ``test_react_graph.py`` 覆盖。
"""

import pytest

from app.agents.omni_agent import OmniAgent
from app.framework.tools import Tool, ToolContext, ToolRegistry, ToolResult, ToolSpec
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
        self.plan_calls = 0

    async def chat_with_tools(self, capability, messages, tools, system=""):
        self.seen_messages.append([dict(m) for m in messages])
        self.calls += 1
        if self.calls <= len(self.script):
            return self.script[self.calls - 1]
        return {"content": "结束", "tool_calls": []}

    async def chat(self, capability, prompt, system=""):
        """max 档的计划产出调用。返非 JSON → 规划失败 → 退化为 standard 语义，
        让预算类用例的轮次算术不被计划驱动干扰。"""
        self.plan_calls += 1
        return "not a plan"


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

async def test_normal_search_batch_stops_before_a_second_llm_round(monkeypatch):
    events, state, gw = await _run(
        [{"content": "", "tool_calls": [_call("shopping.search", {"query": "蓝牙耳机"})]},
         {"content": "信息足够了：TestBrand 旗舰最合适", "tool_calls": []}],
        [_SearchTool()], monkeypatch=monkeypatch)
    kinds = [e["type"] for e in events]
    # 普通模式的商品检索现在是一个受控批次：首个成功 search 后直接收敛，
    # 不再让模型为了生成终稿而进入第二轮工具决策。正式 SSE 由 ResponseAgent
    # 基于工具记录生成流式回答；OmniAgent 薄壳仅暴露工具过程与完成事件。
    assert kinds == ["status", "tool_result", "done"], kinds
    assert gw.calls == 1
    assert state.retrieved_products and state.retrieved_products[0]["product_id"] == "P-A"
    # 工具转录不再写进 context_prompt：SSE 最终回答由 AnswerContextAssembler
    # 读取受控商品/证据状态生成，避免 scratchpad 泄漏。
    assert not state.context_prompt
    # 循环不产终稿：由 SSE ResponseAgent 基于受控工具结果生成，避免 scratchpad 泄漏。
    assert not state.answer_draft
    assert not state.answer, f"循环不应写终稿，实际: {state.answer!r}"
    assert any(m.get("role") == "tool" for m in state.messages)
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in state.messages)


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

async def test_budget_normal_two_rounds(monkeypatch):
    script = [{"content": "", "tool_calls": [_call("order.list", {"limit": i})]} for i in range(10)]
    events, state, gw = await _run(script, [_OrderListTool()], monkeypatch=monkeypatch)
    # 常规模式限制 2 轮：材料足够时应尽快交付，避免无意义工具循环。
    assert gw.calls == 2, gw.calls
    assert events[-1]["type"] == "done" and events[-1]["rounds"] == 3
    # 图内不流式：不再产 token 事件，终稿由 SSE 层的 ResponseAgent 负责。
    # 本例脚本每轮都还在调工具，所以没有草稿，也不应有 answer 事件。
    assert not any(e["type"] == "token" for e in events)
    assert not any(e["type"] == "answer" for e in events)
    assert not (state.answer or "").strip()
    assert not (state.answer_draft or "").strip()


async def test_budget_deep_think_four_rounds(monkeypatch):
    script = [{"content": "", "tool_calls": [_call("order.list", {"limit": i})]} for i in range(20)]
    events, _, gw = await _run(script, [_OrderListTool()], deep_think=True, monkeypatch=monkeypatch)
    assert gw.calls == 4, gw.calls          # 深度思考最多 4 轮
    assert gw.plan_calls == 1               # 首轮尝试产计划（本例规划失败为退化路径）
    assert events[-1]["rounds"] == 5


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
