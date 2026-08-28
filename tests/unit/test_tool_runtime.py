"""受控工具运行时：预算、范围、重复检索与结果归并。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.framework.tools.protocols import ToolResult
from app.schemas.workflow import RetrievalPlan, SubQuery, WorkflowState
from app.workflow.react.runtime import ToolPolicy, ToolRuntime, runtime_context_summary


def _registry(*, permission: str = "read", invoke=None):
    spec = SimpleNamespace(permission=permission, category="shopping", parameters={})
    tool = SimpleNamespace(spec=spec)
    return SimpleNamespace(
        get_optional=lambda _name: tool,
        invoke=invoke or AsyncMock(return_value=ToolResult(message="ok")),
    )


def test_exact_lock_blocks_generic_search():
    state = WorkflowState(
        user_query="介绍 iPhone", retrieval_scope="exact_product",
        resolved_product_ids=["p_iphone"], focus_product_id="p_iphone",
    )
    ToolPolicy.initialise(state, mode="deep")
    prepared = ToolPolicy.prepare(
        state, {"name": "shopping.search", "args": {"query": "iPhone"}}, _registry(),
    )
    assert "无需泛搜索" in prepared.blocked_reason


def test_equivalent_search_is_deduplicated_after_normalisation():
    state = WorkflowState(user_query="干皮保湿面霜")
    ToolPolicy.initialise(state, mode="deep")
    state.tool_ledger.append({
        "name": "shopping.search", "group_id": "main", "query": "干皮保湿面霜", "status": "success",
    })
    prepared = ToolPolicy.prepare(
        state, {"name": "shopping.search", "args": {"query": "干皮 保湿面霜"}}, _registry(),
    )
    assert "无需重复搜索" in prepared.blocked_reason


def test_deep_search_is_bound_to_next_router_group_when_model_uses_a_generic_query():
    """多目标请求不能让 ReAct 的泛词搜索反复落在同一个 main 组。"""
    state = WorkflowState(
        user_query="零食和饮品都想要", mode="max",
        retrieval_plan=RetrievalPlan(sub_queries=[
            SubQuery(role="零食", query="低糖高蛋白零食"),
            SubQuery(role="饮品", query="低糖饮品"),
        ]),
    )
    ToolPolicy.initialise(state, mode="deep")
    first = ToolPolicy.prepare(
        state, {"name": "shopping.search", "args": {"query": "低负担食品"}}, _registry(),
    )
    assert first.group_id == "plan:1"
    assert first.call["args"]["query"] == "低糖高蛋白零食"
    state.tool_ledger.append({"name": "shopping.search", "group_id": "plan:1", "status": "success"})
    second = ToolPolicy.prepare(
        state, {"name": "shopping.search", "args": {"query": "再找点喝的"}}, _registry(),
    )
    assert second.group_id == "plan:2"
    assert second.call["args"]["query"] == "低糖饮品"


def test_same_product_dossier_runs_once_per_request():
    state = WorkflowState(
        user_query="适合拍照吗", retrieval_scope="exact_product",
        resolved_product_ids=["p_phone"], focus_product_id="p_phone",
    )
    ToolPolicy.initialise(state, mode="deep")
    state.tool_ledger.append({"name": "shopping.product_dossier", "product_id": "p_phone", "status": "success"})
    prepared = ToolPolicy.prepare(
        state, {"name": "shopping.product_dossier", "args": {"product_id": "p_phone", "focus": "reviews"}},
        _registry(),
    )
    assert "已经建立" in prepared.blocked_reason


def test_runtime_preserves_successful_candidates_when_later_tool_fails():
    async def invoke(name, _args, ctx):
        if name == "shopping.search":
            ctx.state.retrieved_products = [{"product_id": "p1", "title": "商品1"}]
            return ToolResult(message="找到商品")
        return ToolResult(ok=False, error="provider down")

    state = WorkflowState(user_query="面霜", mode="max")
    reg = _registry(invoke=invoke)
    with patch("app.providers.tools.get_tool_registry", return_value=reg):
        asyncio.run(ToolRuntime.execute_batch(state, [
            {"id": "s1", "name": "shopping.search", "args": {"query": "保湿面霜"}},
            {"id": "s2", "name": "shopping.detail", "args": {"product_id": "p1"}},
        ]))

    assert [item["product_id"] for item in state.retrieved_products] == ["p1"]
    assert [item["status"] for item in state.tool_ledger] == ["success", "failed"]


def test_runtime_context_exposes_only_safe_summary():
    state = WorkflowState(user_query="面霜", retrieval_scope="product_family", resolved_product_ids=["p1"])
    ToolPolicy.initialise(state, mode="deep")
    state.tool_ledger.append({"name": "shopping.search", "group_id": "main", "status": "success", "summary": "已找到候选"})
    summary = runtime_context_summary(state)
    assert "可信商品范围" in summary
    assert "已执行" in summary
    assert "args" not in summary


def test_normal_multi_target_is_one_controlled_parallel_batch():
    """普通模式不进 ReAct，但 Router 拆出的独立目标仍可在同一批次内执行。"""
    seen: list[tuple[str, str]] = []

    async def invoke(name, args, _ctx):
        seen.append((name, args["query"]))
        return ToolResult(message=f"完成 {args['query']}")

    state = WorkflowState(
        user_query="上衣裤子搭一套",
        retrieval_plan=RetrievalPlan(sub_queries=[
            SubQuery(role="上衣", query="休闲上衣"),
            SubQuery(role="裤子", query="休闲长裤"),
        ]),
    )
    with patch("app.providers.tools.get_tool_registry", return_value=_registry(invoke=invoke)):
        asyncio.run(ToolRuntime.run_normal_search(state))

    assert seen == [("shopping.search", "休闲上衣"), ("shopping.search", "休闲长裤")]
    assert [item["group_id"] for item in state.tool_ledger] == ["plan:1", "plan:2"]
    assert state.tool_budget["limits"]["shopping.search"] == 2


def test_batch_reservation_blocks_duplicate_dossier_before_execution():
    """同一模型回复不能借不同 focus 重复建立同一单品档案。"""
    invoked: list[str] = []

    async def invoke(name, _args, _ctx):
        invoked.append(name)
        return ToolResult(message="档案已建立")

    state = WorkflowState(
        user_query="适合拍照吗", mode="max", retrieval_scope="exact_product",
        resolved_product_ids=["p_phone"], focus_product_id="p_phone",
    )
    with patch("app.providers.tools.get_tool_registry", return_value=_registry(invoke=invoke)):
        asyncio.run(ToolRuntime.execute_batch(state, [
            {"id": "d1", "name": "shopping.product_dossier", "args": {"product_id": "p_phone", "focus": "reviews"}},
            {"id": "d2", "name": "shopping.product_dossier", "args": {"product_id": "p_phone", "focus": "risks"}},
        ]))

    assert invoked == ["shopping.product_dossier"]
    assert [item["status"] for item in state.tool_ledger] == ["success", "blocked"]


def test_read_tool_cannot_write_legacy_prompt_back_to_main_state():
    """隔离工具的兼容 prompt 不能污染最终 AnswerContext 的输入边界。"""

    async def invoke(_name, _args, ctx):
        ctx.state.context_prompt = "[工具全文] 不应回写到主状态"
        ctx.state.retrieved_products = [{"product_id": "p1", "title": "商品1"}]
        return ToolResult(message="找到商品")

    state = WorkflowState(user_query="找面霜", context_prompt="[追问约束] 预算 300")
    with patch("app.providers.tools.get_tool_registry", return_value=_registry(invoke=invoke)):
        asyncio.run(ToolRuntime.execute_batch(state, [
            {"id": "s1", "name": "shopping.search", "args": {"query": "保湿面霜"}},
        ]))

    assert state.context_prompt == "[追问约束] 预算 300"
    assert [item["product_id"] for item in state.retrieved_products] == ["p1"]
