"""Phase 7 深度检索工具单测 —— 子管线 / state 写回 / 降级 / intent_hint。"""

import pytest

from app.framework.tools import ToolContext
from app.providers.tools.shopping import SearchProductsTool
from app.schemas.workflow import WorkflowState


async def test_deep_search_returns_products_and_writes_state():
    state = WorkflowState(user_id="u1")
    ctx = ToolContext(user_id="u1", state=state)
    res = await SearchProductsTool().run(ctx, query="蓝牙耳机", top_k=5)
    assert res.ok
    assert res.data["products"], "深管线应返回商品"
    assert all(p.get("product_id") for p in res.data["products"])
    assert "深度检索" in res.message
    # 深管线产物含 decision 字段（决策评分经 DecisionAgent 写回）
    assert any(p.get("decision_score") is not None for p in res.data["products"]), \
        "至少一件商品应带 decision_score"
    assert state.decision_results, "decision_results 应写回主 state"
    # 写回主 state（供最终 generate_stream / 前端商品卡）
    assert state.retrieved_products
    assert state.evidence_list  # 证据同步写回


async def test_deep_search_state_merge_dedupes():
    state = WorkflowState(user_id="u1")
    ctx = ToolContext(user_id="u1", state=state)
    r1 = await SearchProductsTool().run(ctx, query="蓝牙耳机", top_k=3)
    first_pid = r1.data["products"][0]["product_id"]
    n_after_first = len(state.retrieved_products)
    # 二次检索同词 → 去重不翻倍
    await SearchProductsTool().run(ctx, query="蓝牙耳机", top_k=3)
    pids = [p.get("product_id") for p in state.retrieved_products]
    assert len(pids) == len(set(pids)), "写回必须去重"
    assert first_pid in pids
    assert len(state.retrieved_products) <= n_after_first + 3


async def test_pipeline_failure_falls_back_to_shallow(monkeypatch):
    # P0-1 后子管线从 framework 能力注册表取函数，patch 注册表而非 graph 模块属性
    from app.framework.orchestration import capabilities as caps

    async def _boom(sub):
        raise RuntimeError("pipeline down")

    monkeypatch.setitem(caps._CAPABILITIES, "retrieval", _boom)
    res = await SearchProductsTool().run(ToolContext(user_id="u1"), query="蓝牙耳机")
    assert res.ok
    assert "找到" in res.message  # 浅层兜底文案


async def test_intent_hint_passed_to_sub_state(monkeypatch):
    from app.framework.orchestration import capabilities as caps

    captured = {}

    async def _cap_retrieval(sub):
        captured["intent"] = sub.intent
        captured["top_k"] = sub.retrieval_plan.top_k
        sub.retrieved_products = [{"product_id": "P1", "title": "t", "brand": "b", "price": 1}]
        sub.evidence_list = []
        return sub

    async def _identity_async(sub):
        return sub

    monkeypatch.setitem(caps._CAPABILITIES, "retrieval", _cap_retrieval)
    monkeypatch.setitem(caps._CAPABILITIES, "reranker", _identity_async)
    monkeypatch.setitem(caps._CAPABILITIES, "evidence_check", lambda sub: sub)
    monkeypatch.setitem(caps._CAPABILITIES, "decision", _identity_async)
    res = await SearchProductsTool().run(ToolContext(user_id="u1"),
                                         query="降噪耳机", intent_hint="compare", top_k=4)
    assert res.ok and captured["intent"] == "compare"
    assert captured["top_k"] >= 8
