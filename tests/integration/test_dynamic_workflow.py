"""Phase 4+5 动态图端到端 —— MOCK 模式、flag on、无 Redis/PG（enable_checkpoint=False 旁路缓存）。

覆盖：意图分化路径 / 并行组 / tool: 派发 / Reflect 幻觉回环 / flag on-off 对拍。
"""

import pytest

from app.schemas.workflow import WorkflowState


async def _run(query: str, **kw):
    from app.workflow.graph import run_workflow

    return await run_workflow(user_query=query, enable_checkpoint=False, **kw)


@pytest.fixture
def dyn(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)


def _has_step(state, cap: str) -> bool:
    return any(cap in sid for sid in state.completed_steps)


async def test_chitchat_single_step(dyn):
    state = await _run("你好呀")
    assert state.plan.get("intent") == "chitchat"
    assert len(state.completed_steps) == 1 and _has_step(state, "response")
    assert not _has_step(state, "retrieval")
    assert state.answer


async def test_risk_check_skips_reranker(dyn):
    state = await _run("这款耳机有什么风险和副作用")
    assert state.plan.get("intent") == "risk_check"
    assert _has_step(state, "retrieval") and _has_step(state, "decision")
    assert not _has_step(state, "reranker")
    assert "rerank_ms" not in state.timing


async def test_compare_runs_parallel_group(dyn):
    state = await _run("索尼和Bose对比哪个好")
    assert state.plan.get("intent") == "compare"
    assert _has_step(state, "reranker") and _has_step(state, "evidence_check")
    assert "parallel_g1_ms" in state.timing


async def test_recommend_flag_on_vs_off(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)
    dyn_state = await _run("推荐一款蓝牙耳机")
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", False)
    legacy_state = await _run("推荐一款蓝牙耳机")
    # 对拍：两条路径都产出回答与 harness 报告；MOCK 检索确定性 → 商品数一致
    assert dyn_state.answer and legacy_state.answer
    assert "passed" in dyn_state.harness_report and "passed" in legacy_state.harness_report
    assert len(dyn_state.retrieved_products) == len(legacy_state.retrieved_products)
    # 动态路径完整执行了全链
    for cap in ("retrieval", "reranker", "evidence_check", "decision", "response"):
        assert _has_step(dyn_state, cap), f"missing {cap}"


async def test_tool_capability_dispatch():
    """supervisor 派发 tool:<name> → ToolRegistry.invoke → skill_executions 落 trace。"""
    import app.workflow.graph as g
    from app.framework.tools import Tool, ToolResult, ToolSpec
    from app.providers.tools import get_tool_registry

    class _DynDummyTool(Tool):
        spec = ToolSpec(name="test.dyn_dummy", category="test", description="dummy")

        async def run(self, ctx):
            return ToolResult(message="ok")

    reg = get_tool_registry()
    if reg.get_optional("test.dyn_dummy") is None:
        reg.register(_DynDummyTool())

    state = WorkflowState(user_id="u1", plan={
        "steps": [{"step_id": "t1", "capability": "tool:test.dyn_dummy",
                   "depends_on": [], "parallel_group": None, "optional": False}],
        "max_reflects": 1,
    })
    state = await g._node_supervisor(state)
    assert state.completed_steps == ["t1"]
    assert state.skill_executions and state.skill_executions[0]["skill_name"] == "test.dyn_dummy"


async def test_reflect_regenerates_on_hallucination(dyn, monkeypatch):
    """Guard 首轮 fail → 纠正指令重生成一次 → 二轮 pass → END。"""
    import app.workflow.graph as g

    class _FlakyGuard:
        def __init__(self):
            self.calls = 0

        def check(self, state):
            self.calls += 1
            passed = self.calls > 1
            state.harness_report = {
                "schema_valid": True, "evidence_bound": True, "price_accurate": True,
                "risk_warned": True, "honest_on_empty": True, "guard_warnings": [],
                "passed": passed, "failure_source": None if passed else "response_guard",
            }
            return state.harness_report

    guard = _FlakyGuard()
    monkeypatch.setattr(g, "_guard", guard)
    state = await _run("推荐一款蓝牙耳机")
    assert guard.calls == 2               # reflect 评估两轮
    assert state.reflect_count == 1       # 消耗一次反思预算
    assert any(sid.startswith("r1_") for sid in state.completed_steps)  # response 重排执行
    assert "[纠正]" in state.context_prompt
    assert state.harness_report.get("passed") is True
    assert state.answer


# ---- Phase 6-B2: LLM Planner 端到端 ----

async def test_llm_plan_tool_step_e2e(dyn, monkeypatch):
    """MOCK 全链：复杂 query → MockChat 返工具计划 → 工具步执行 + 结果回填 → 合成回答。"""
    monkeypatch.setattr("app.core.config.ENABLE_LLM_PLANNER", True)
    state = await _run("看看我的订单然后推荐个类似的")
    assert state.plan.get("meta", {}).get("planner") == "llm"
    assert state.plan.get("meta", {}).get("trigger") == "multi_step"
    assert any("s1" == sid for sid in state.completed_steps)   # tool:order.list 步
    assert "[工具 order.list 结果]" in state.context_prompt
    assert state.skill_executions and state.skill_executions[0]["skill_name"] == "order.list"
    assert state.answer


async def test_supervisor_tool_step_backfills_context():
    """supervisor 工具步结果回填 context_prompt（供 response 合成）。"""
    import app.workflow.graph as g
    from app.framework.tools import Tool, ToolResult, ToolSpec
    from app.providers.tools import get_tool_registry

    class _BackfillTool(Tool):
        spec = ToolSpec(name="test.backfill", category="test", description="backfill")

        async def run(self, ctx):
            return ToolResult(message="库存充足，放心买～")

    reg = get_tool_registry()
    if reg.get_optional("test.backfill") is None:
        reg.register(_BackfillTool())

    state = WorkflowState(user_id="u1", plan={
        "steps": [{"step_id": "t1", "capability": "tool:test.backfill",
                   "depends_on": [], "parallel_group": None, "optional": False}],
        "max_reflects": 1,
    })
    state = await g._node_supervisor(state)
    assert "[工具 test.backfill 结果]" in state.context_prompt
    assert "库存充足" in state.context_prompt
