"""ReAct 双档同构图的不变量测试。

这三组断言是移植 amap 编排设计时最重要的护栏，任何一条被破坏都意味着设计意图丢失：
1. 两档拓扑必须同构 —— 差异只允许存在于节点实现，不允许出现在图结构上；
2. check_iteration 必须是唯一生效的终止条件 —— 死循环的唯一防线；
3. 只读工具并行 / 含写工具串行 —— 调过的性能行为，不是实现细节。
"""

from __future__ import annotations

import asyncio
import itertools
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.workflow import RetrievalPlan, SubQuery, WorkflowState
from app.workflow.react import get_react_workflow, run_config
from app.workflow.react.nodes.guard import budget_for
from app.workflow.react.nodes.tool import execute_tools


def _graph_signature(graph):
    nodes = sorted(n for n in graph.get_graph().nodes if not n.startswith("__"))
    edges = sorted((e.source, e.target, e.data or "") for e in graph.get_graph().edges)
    return nodes, edges


def _fake_registry(*, permission: str = "read", invoke=None, actions=None):
    """最小工具注册表替身。``permission`` 决定 execute_tools 走并行还是串行。

    ``invoke`` 必须包 staticmethod：普通函数赋给类属性会被绑定成方法、
    多传一个 self（AsyncMock 不是描述符，所以不受影响，容易踩坑）。
    """
    spec = type("Spec", (), {"permission": permission, "category": "shopping",
                             "timeout_ms": 8000})()
    tool = type("Tool", (), {"spec": spec})()
    result = type("TR", (), {"ok": True, "data": {}, "message": "ok", "error": "",
                             "actions": actions or []})()
    return type("Reg", (), {
        "openai_schemas": lambda self, **kw: [],
        "get_optional": lambda self, name: tool,
        "invoke": staticmethod(invoke) if invoke else AsyncMock(return_value=result),
    })()


# ══════════════════════════════════════════════════════════════════════
# 1. 拓扑同构
# ══════════════════════════════════════════════════════════════════════

def test_two_tiers_share_identical_topology():
    """standard 与 max 的节点集与边集必须逐一相等。

    amap 的 standard.py / max.py 是两份独立构图代码却保持 8 节点完全同名，
    本移植用同一个 build() 保证这点。这条断言防的是"有人给某一档偷偷加了节点"。
    """
    std_nodes, std_edges = _graph_signature(get_react_workflow("standard"))
    max_nodes, max_edges = _graph_signature(get_react_workflow("max"))
    assert std_nodes == max_nodes, f"节点漂移: {set(std_nodes) ^ set(max_nodes)}"
    assert std_edges == max_edges, f"边漂移: {set(std_edges) ^ set(max_edges)}"


def test_two_tiers_differ_only_in_two_nodes():
    """两档的节点实现只允许在 invoke_llm / check_completion 上不同。

    同构断言只看图结构，看不出某一档把共享节点换成了别的实现。
    这条直接比节点函数对象，钉住差异面。
    """
    from app.workflow.react.max.graph import MAX_NODES
    from app.workflow.react.standard.graph import STANDARD_NODES

    differing = {k for k in STANDARD_NODES if STANDARD_NODES[k] is not MAX_NODES[k]}
    assert differing == {"invoke_llm", "check_completion"}, differing


def test_expected_six_nodes():
    """节点集就是计划里定下的 6 个，多一个少一个都要显式改测试。"""
    nodes, _ = _graph_signature(get_react_workflow("standard"))
    assert nodes == ["check_completion", "check_iteration", "execute_tools",
                     "finalize", "invoke_llm", "prepare"]


def test_unknown_mode_falls_back_to_standard():
    """非法档位回退而不抛错 —— 档位来自请求参数，不该 500。"""
    assert _graph_signature(get_react_workflow("nonsense")) == \
        _graph_signature(get_react_workflow("standard"))


# ══════════════════════════════════════════════════════════════════════
# 2. 回环闸门
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mode", ["standard", "max"])
def test_never_converging_llm_stops_at_budget(mode):
    """LLM 每轮都返回全新工具调用（签名不重复）时，必须恰好在预算轮收尾。

    这是死循环的唯一防线。签名不重复是刻意的 —— 要绕开防循环那道保险，
    单独验证预算闸门本身有效。
    """
    counter = itertools.count()

    async def never_converge(*_a, **_kw):
        i = next(counter)
        return {"tool_calls": [{"id": f"c{i}", "name": "shopping.search",
                                "args": {"query": f"q{i}"}}], "content": ""}

    async def no_plan(*_a, **_kw):
        return "not json"  # max 档规划失败 -> 退化 standard 语义，仍受预算约束

    gateway = type("G", (), {"chat_with_tools": staticmethod(never_converge),
                             "chat": staticmethod(no_plan)})()
    with patch("app.model_gateway.gateway.get_model_gateway", return_value=gateway), \
         patch("app.providers.tools.get_tool_registry", return_value=_fake_registry()):
        out = asyncio.run(get_react_workflow(mode).ainvoke(
            WorkflowState(user_query="永不收敛", mode=mode), config=run_config(mode)))

    assert out["transition"] == "finalize"
    llm_rounds = sum(1 for t in out["trace_steps"] if t["action"] == "invoke_llm")
    # 新运行时除回合上限外还有 search 预算：普通模式 1 次、深度模式 3 次。
    expected = 1 if mode == "standard" else 3
    assert llm_rounds == expected, f"{mode} 档应在 search 预算耗尽后收敛，实际 {llm_rounds}"


def test_repeated_tool_calls_force_stop():
    """LLM 重复同一组调用时防循环立即收尾，不烧到预算上限。"""
    async def always_same(*_a, **_kw):
        return {"tool_calls": [{"id": "c", "name": "shopping.search",
                                "args": {"query": "同一个"}}], "content": ""}

    gateway = type("G", (), {"chat_with_tools": staticmethod(always_same)})()
    with patch("app.model_gateway.gateway.get_model_gateway", return_value=gateway), \
         patch("app.providers.tools.get_tool_registry", return_value=_fake_registry()):
        out = asyncio.run(get_react_workflow("standard").ainvoke(
            WorkflowState(user_query="重复调用", mode="standard"),
            config=run_config("standard")))

    assert any(item["status"] in {"blocked", "success"} for item in out["tool_ledger"])
    llm_rounds = sum(1 for t in out["trace_steps"] if t["action"] == "invoke_llm")
    assert llm_rounds == 1, "普通模式应在唯一检索预算后直接收敛"


def test_recursion_limit_exceeds_budget_need():
    """LangGraph 的 recursion_limit 必须宽于预算所需，否则框架会抢在闸门前抛错。

    每轮消耗 3 个 superstep（check_iteration / invoke_llm / execute_tools）。
    ``OMNICART_AGENT_LOOP_DEEP_ROUNDS`` 是 env 可配的，这条断言防的是运维调高预算后
    静默撞上 LangGraph 默认上限 25。
    """
    for mode in ("standard", "max"):
        assert run_config(mode)["recursion_limit"] > budget_for(mode) * 3


# ══════════════════════════════════════════════════════════════════════
# 3. 工具执行语义
# ══════════════════════════════════════════════════════════════════════

def test_independent_router_search_groups_run_in_parallel():
    """只有 Router 明确标为独立目标的 search 才能并行。"""
    async def slow_invoke(_name, _args, _ctx):
        await asyncio.sleep(0.05)
        return type("TR", (), {"ok": True, "data": {}, "message": "ok",
                               "error": "", "actions": []})()

    state = WorkflowState(user_query="对比", retrieval_plan=RetrievalPlan(sub_queries=[
        SubQuery(role="目标1", query="1"), SubQuery(role="目标2", query="2"), SubQuery(role="目标3", query="3"),
    ]), pending_tool_calls=[
        {"id": "a", "name": "shopping.search", "args": {"query": "1"}},
        {"id": "b", "name": "shopping.search", "args": {"query": "2"}},
        {"id": "c", "name": "shopping.search", "args": {"query": "3"}},
    ])
    reg = _fake_registry(permission="read", invoke=slow_invoke)
    with patch("app.providers.tools.get_tool_registry", return_value=reg):
        t0 = time.perf_counter()
        asyncio.run(execute_tools(state))
        elapsed = time.perf_counter() - t0

    assert elapsed < 0.12, f"3 个只读工具应并行（约 0.05s），实际 {elapsed:.3f}s"
    assert sum(1 for m in state.messages if m["role"] == "tool") == 3


def test_write_tools_run_serially_in_order():
    """含写操作串行且保持顺序 —— 购物车/订单状态变更的顺序必须确定。"""
    order: list[str] = []

    async def recording_invoke(name, _args, _ctx):
        order.append(name)
        await asyncio.sleep(0.01)
        return type("TR", (), {"ok": True, "data": {}, "message": "ok",
                               "error": "", "actions": []})()

    state = WorkflowState(user_query="加购再改数量", pending_tool_calls=[
        {"id": "a", "name": "cart.add", "args": {}},
        {"id": "b", "name": "cart.update_qty", "args": {}},
    ])
    reg = _fake_registry(permission="write", invoke=recording_invoke)
    with patch("app.providers.tools.get_tool_registry", return_value=reg):
        asyncio.run(execute_tools(state))

    assert order == ["cart.add", "cart.update_qty"], f"顺序被打乱: {order}"


def test_tool_exception_backfills_error_and_continues():
    """单工具异常回填错误文本继续，不中断整轮。"""
    async def boom(name, _args, _ctx):
        if name == "shopping.search":
            raise RuntimeError("provider down")
        return type("TR", (), {"ok": True, "data": {}, "message": "ok",
                               "error": "", "actions": []})()

    state = WorkflowState(user_query="x", pending_tool_calls=[
        {"id": "a", "name": "shopping.search", "args": {"query": "x"}},
        {"id": "b", "name": "cart.add", "args": {}},
    ])
    reg = _fake_registry(permission="write", invoke=boom)
    with patch("app.providers.tools.get_tool_registry", return_value=reg):
        asyncio.run(execute_tools(state))

    tool_msgs = [m["content"] for m in state.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2, "异常工具也要回填，否则 OpenAI 协议缺 tool 响应"
    assert "[工具失败]" in tool_msgs[0]
    assert any(t["status"] == "failed" for t in state.trace_steps)


def test_tool_actions_accumulated_for_frontend():
    """交互动作必须累计透传 —— 不透传会让多规格商品的规格选择按钮消失。"""
    state = WorkflowState(user_query="加购", pending_tool_calls=[
        {"id": "a", "name": "cart.add", "args": {}},
    ])
    reg = _fake_registry(permission="write",
                         actions=[{"type": "sku_option", "product_id": "P1"}])
    with patch("app.providers.tools.get_tool_registry", return_value=reg):
        asyncio.run(execute_tools(state))

    assert state.tool_actions == [{"type": "sku_option", "product_id": "P1"}]


def test_trace_latency_is_measured_not_zero():
    """trace 的 latency_ms 必须实测 —— 原 omni_agent._trace 硬编码 0，
    导致深度思考轨迹面板每步耗时都显示 0。"""
    async def slow_invoke(_name, _args, _ctx):
        await asyncio.sleep(0.02)
        return type("TR", (), {"ok": True, "data": {}, "message": "ok",
                               "error": "", "actions": []})()

    state = WorkflowState(user_query="x", pending_tool_calls=[
        {"id": "a", "name": "shopping.search", "args": {}},
    ])
    reg = _fake_registry(invoke=slow_invoke)
    with patch("app.providers.tools.get_tool_registry", return_value=reg):
        asyncio.run(execute_tools(state))

    tool_traces = [t for t in state.trace_steps if t["action"] == "shopping.search"]
    assert tool_traces and tool_traces[0]["latency_ms"] > 0


# ══════════════════════════════════════════════════════════════════════
# 4. 闲聊短路
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mode", ["standard", "max"])
def test_chitchat_short_circuits_without_llm_call(mode):
    """闲聊不该带着一整套工具 schema 去问 LLM。

    也守住 intent 落 state 这条链：ResponseAgent 的闲聊分支门控是
    ``state.intent == "chitchat"``，prepare 若不写 intent，深度思考路径下
    "你好"就只能由无商品的模板兜底。
    """
    called = {"n": 0}

    async def counting_chat(*_a, **_kw):
        called["n"] += 1
        return {"tool_calls": [], "content": ""}

    async def fake_qu(*_a, **_kw):
        return {"intent": "chitchat"}

    gateway = type("G", (), {"chat_with_tools": staticmethod(counting_chat),
                             "chat": staticmethod(counting_chat)})()
    with patch("app.model_gateway.gateway.get_model_gateway", return_value=gateway), \
         patch("app.providers.tools.get_tool_registry", return_value=_fake_registry()), \
         patch("app.agents.router_agent.aunderstand_query", new=fake_qu):
        out = asyncio.run(get_react_workflow(mode).ainvoke(
            WorkflowState(user_query="你好", mode=mode), config=run_config(mode)))

    assert called["n"] == 0, f"闲聊不应调用模型，实际 {called['n']} 次"
    assert out["intent"] == "chitchat", "intent 必须落到 state，否则闲聊分支不触发"
    assert any(t["action"] == "chitchat" for t in out["trace_steps"])
    assert not (out["answer_draft"] or "").strip(), "闲聊不产草稿，终稿交 ResponseAgent"


def test_non_chitchat_still_calls_llm():
    """短路只对闲聊生效，正常购物意图必须照常进循环。"""
    called = {"n": 0}

    async def counting_chat(*_a, **_kw):
        called["n"] += 1
        return {"tool_calls": [], "content": "推荐这款"}

    async def fake_qu(*_a, **_kw):
        return {"intent": "recommend"}

    gateway = type("G", (), {"chat_with_tools": staticmethod(counting_chat)})()
    with patch("app.model_gateway.gateway.get_model_gateway", return_value=gateway), \
         patch("app.providers.tools.get_tool_registry", return_value=_fake_registry()), \
         patch("app.agents.router_agent.aunderstand_query", new=fake_qu):
        out = asyncio.run(get_react_workflow("standard").ainvoke(
            WorkflowState(user_query="推荐面霜", mode="standard"),
            config=run_config("standard")))

    assert called["n"] >= 1
    assert out["intent"] == "recommend"
