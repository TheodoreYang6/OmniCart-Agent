"""Phase 4+5 动态编排单测 —— ExecutionPlan / RulePlanner / Reflect 决策。"""

import pytest

from app.framework.orchestration import ExecutionPlan, PlanStep, RulePlanner
from app.schemas.workflow import WorkflowState


def _caps(plan: ExecutionPlan) -> list[str]:
    return [s.capability for s in plan.steps]


# ---- ExecutionPlan.next_ready ----

def test_next_ready_serial_order():
    plan = ExecutionPlan(steps=[
        PlanStep(step_id="a", capability="retrieval"),
        PlanStep(step_id="b", capability="decision", depends_on=["a"]),
    ])
    assert [s.step_id for s in plan.next_ready(set())] == ["a"]
    assert [s.step_id for s in plan.next_ready({"a"})] == ["b"]
    assert plan.next_ready({"a", "b"}) == []


def test_next_ready_parallel_group_batches_together():
    plan = ExecutionPlan(steps=[
        PlanStep(step_id="a", capability="retrieval"),
        PlanStep(step_id="b", capability="reranker", depends_on=["a"], parallel_group="g1"),
        PlanStep(step_id="c", capability="evidence_check", depends_on=["a"], parallel_group="g1"),
        PlanStep(step_id="d", capability="decision", depends_on=["b", "c"]),
    ])
    ready = plan.next_ready({"a"})
    assert {s.step_id for s in ready} == {"b", "c"}
    assert [s.step_id for s in plan.next_ready({"a", "b", "c"})] == ["d"]


def test_next_ready_blocked_by_dependency():
    plan = ExecutionPlan(steps=[
        PlanStep(step_id="a", capability="retrieval"),
        PlanStep(step_id="b", capability="decision", depends_on=["a"]),
    ])
    # a 未完成时 b 不就绪
    assert [s.step_id for s in plan.next_ready(set())] == ["a"]


# ---- RulePlanner 模板 ----

async def test_planner_chitchat():
    plan = await RulePlanner().plan(WorkflowState(intent="chitchat"))
    assert _caps(plan) == ["response"]


async def test_planner_risk_check_skips_reranker():
    plan = await RulePlanner().plan(WorkflowState(intent="risk_check"))
    assert _caps(plan) == ["retrieval", "evidence_check", "decision", "response"]
    assert "reranker" not in _caps(plan)


async def test_planner_compare_parallel_group():
    plan = await RulePlanner().plan(WorkflowState(intent="compare"))
    assert _caps(plan) == ["retrieval", "reranker", "evidence_check", "decision", "response"]
    by_cap = {s.capability: s for s in plan.steps}
    assert by_cap["reranker"].parallel_group == "g1"
    assert by_cap["evidence_check"].parallel_group == "g1"
    # 并行组两步依赖相同（retrieval），decision 依赖并行组两步
    assert by_cap["reranker"].depends_on == by_cap["evidence_check"].depends_on
    assert set(by_cap["decision"].depends_on) == {by_cap["reranker"].step_id, by_cap["evidence_check"].step_id}


async def test_planner_default_full_chain():
    for intent in ("recommend", "alternative", "compatibility_check", ""):
        plan = await RulePlanner().plan(WorkflowState(intent=intent))
        assert _caps(plan) == ["retrieval", "reranker", "evidence_check", "decision", "response"]


async def test_planner_image_prepends_visual():
    plan = await RulePlanner().plan(WorkflowState(intent="recommend", image_url="http://x/1.jpg"))
    assert _caps(plan)[0] == "visual"
    # visual 之后的第一步依赖 visual
    assert plan.steps[1].depends_on == [plan.steps[0].step_id]


# ---- QU V2 新意图模板 ----

async def test_planner_bundle_uses_multi_query():
    from app.schemas.workflow import SubQuery

    st = WorkflowState(intent="bundle", user_query="上衣裤子鞋搭一套")
    st.retrieval_plan.sub_queries = [SubQuery(role="上衣", query="上衣"),
                                     SubQuery(role="鞋", query="鞋")]
    plan = await RulePlanner().plan(st)
    assert _caps(plan) == ["multi_query_retrieval", "reranker", "evidence_check",
                           "decision", "response"]
    assert "2 路" in plan.rationale


async def test_planner_replenish_prepends_order_tool():
    plan = await RulePlanner().plan(WorkflowState(intent="replenish"))
    assert _caps(plan) == ["tool:order.list", "retrieval", "reranker",
                           "evidence_check", "decision", "response"]


async def test_planner_knowledge_light_chain():
    plan = await RulePlanner().plan(WorkflowState(intent="knowledge"))
    assert _caps(plan) == ["retrieval", "response"]
    assert plan.meta.get("knowledge") is True


async def test_planner_gift_same_as_recommend():
    plan = await RulePlanner().plan(WorkflowState(intent="gift"))
    assert _caps(plan) == ["retrieval", "reranker", "evidence_check", "decision", "response"]


# ---- 对比目标分解（compare 深化）----

def test_extract_compare_targets():
    from app.framework.orchestration.planner import extract_compare_targets as ect

    assert ect("索尼和Bose的耳机对比哪个好") == ["索尼", "Bose的耳机"]
    assert ect("对airpods和huawei freebuds pro5做对比") == ["airpods", "huawei freebuds pro5"]
    assert ect("iphone vs 华为mate70") == ["iphone", "华为mate70"]
    assert ect("华为和索尼哪个好") == ["华为", "索尼"]
    # 句首"对比"引导词（灰度手测实锤的 bug：之前只剥"对"字产生 "比airpods"）
    assert ect("对比airpods和huawei freebuds pro5") == ["airpods", "huawei freebuds pro5"]
    assert ect("比较一下索尼与Bose") == ["索尼", "Bose"]
    # FollowUpEngine 拼接上下文污染 → 只取首行
    assert ect("对比airpods和huawei freebuds pro5\n\n[上下文] 用户之前在看耳机") == \
        ["airpods", "huawei freebuds pro5"]
    assert ect("推荐一款蓝牙耳机") == []   # 无分隔符 → 提不出
    assert ect("") == []


async def test_planner_compare_with_targets_uses_compare_retrieval():
    plan = await RulePlanner().plan(WorkflowState(
        intent="compare", user_query="对airpods和huawei freebuds pro5做对比"))
    assert _caps(plan) == ["compare_retrieval", "reranker", "evidence_check", "decision", "response"]
    assert plan.meta["compare_targets"] == ["airpods", "huawei freebuds pro5"]


async def test_planner_compare_without_targets_falls_back():
    plan = await RulePlanner().plan(WorkflowState(intent="compare", user_query="帮我对比一下"))
    assert _caps(plan)[0] == "retrieval"
    assert "compare_targets" not in plan.meta


async def test_compare_retrieval_interleaves_and_annotates(monkeypatch):
    """两路 fake 检索 → 交替合并 + 命中数注入 context_prompt。"""
    import app.workflow.graph as g

    async def fake_retrieval(sub):
        if "airpods" in sub.user_query.lower():
            sub.retrieved_products = [
                {"product_id": "P-APPLE", "brand": "Apple 苹果", "title": "Apple AirPods Pro 3"}]
            sub.evidence_list = [{"product_id": "P-APPLE", "text": "降噪评测"}]
        else:
            sub.retrieved_products = [
                {"product_id": "P-HW", "brand": "华为", "title": "华为HUAWEI FreeBuds Pro 5"},
                {"product_id": "P-OTHER", "brand": "QCY", "title": "QCY MeloBuds"}]
            sub.evidence_list = []
        return sub

    monkeypatch.setattr(g, "_node_retrieval", fake_retrieval)
    from app.framework.orchestration import RulePlanner as _RP

    state = WorkflowState(intent="compare", user_query="对airpods和huawei freebuds pro5做对比")
    plan = await _RP().plan(state)
    state.plan = plan.model_dump()
    state = await g._node_compare_retrieval(state)

    pids = [p["product_id"] for p in state.retrieved_products]
    assert pids == ["P-APPLE", "P-HW", "P-OTHER"]     # 交替合并，双目标头部在前
    assert "[对比检索结果" in state.context_prompt
    assert "「airpods」库内命中 1 件" in state.context_prompt
    assert state.evidence_list == [{"product_id": "P-APPLE", "text": "降噪评测"}]
    assert "compare_retrieval_ms" in state.timing


async def test_compare_retrieval_zero_hit_marks_unavailable(monkeypatch):
    """某目标零命中 → 提示词明确标注无法对比（链路验证的否定，非 LLM 臆断）。"""
    import app.workflow.graph as g

    async def fake_retrieval(sub):
        sub.retrieved_products = [
            {"product_id": "P-X", "brand": "QCY", "title": "QCY MeloBuds"}]
        sub.evidence_list = []
        return sub

    monkeypatch.setattr(g, "_node_retrieval", fake_retrieval)
    from app.framework.orchestration import RulePlanner as _RP

    state = WorkflowState(intent="compare", user_query="索尼和Bose的耳机对比哪个好")
    plan = await _RP().plan(state)
    state.plan = plan.model_dump()
    state = await g._node_compare_retrieval(state)
    assert "「索尼」库内命中 0 件（未找到，请明确告知用户无法对比此目标）" in state.context_prompt


# ---- Reflect 决策（_node_reflect + reflect_next + _requeue）----

class _FakeGuard:
    """可编程 Guard：按调用次序返回 passed 序列。"""

    def __init__(self, passed_seq):
        self._seq = list(passed_seq)

    def check(self, state):
        passed = self._seq.pop(0) if self._seq else True
        state.harness_report = {
            "schema_valid": True, "evidence_bound": True, "price_accurate": True,
            "risk_warned": True, "honest_on_empty": True, "guard_warnings": [],
            "passed": passed, "failure_source": None if passed else "response_guard",
        }
        return state.harness_report


async def _run_reflect(state, monkeypatch, passed_seq):
    import app.workflow.graph as g

    monkeypatch.setattr(g, "_guard", _FakeGuard(passed_seq))
    state = await g._node_reflect(state)
    route = g.get_route("reflect_next")(state)
    return state, route


async def test_reflect_guard_fail_requeues_response(monkeypatch):
    plan = await RulePlanner().plan(WorkflowState(intent="recommend"))
    state = WorkflowState(intent="recommend", answer="幻觉回答",
                          retrieved_products=[{"product_id": "P1"}],
                          plan=plan.model_dump(),
                          completed_steps=[s.step_id for s in plan.steps])
    state, route = await _run_reflect(state, monkeypatch, [False])
    assert route == "supervisor"
    assert state.reflect_count == 1
    assert state.answer == "" and "[纠正]" in state.context_prompt
    new_steps = state.plan["steps"][len(plan.steps):]
    assert [s["capability"] for s in new_steps] == ["response"]


async def test_reflect_zero_results_widens_retrieval(monkeypatch):
    plan = await RulePlanner().plan(WorkflowState(intent="recommend"))
    state = WorkflowState(intent="recommend", retrieved_products=[],
                          plan=plan.model_dump(),
                          completed_steps=[s.step_id for s in plan.steps])
    top_k_before = state.retrieval_plan.top_k
    state, route = await _run_reflect(state, monkeypatch, [True])
    assert route == "supervisor"
    assert state.reflect_count == 1
    assert state.retrieval_plan.top_k == top_k_before + 5
    new_caps = [s["capability"] for s in state.plan["steps"][len(plan.steps):]]
    assert new_caps == ["retrieval", "reranker", "evidence_check", "decision", "response"]


async def test_reflect_budget_exhausted_ends(monkeypatch):
    plan = await RulePlanner().plan(WorkflowState(intent="recommend"))
    state = WorkflowState(intent="recommend", answer="仍是幻觉",
                          retrieved_products=[{"product_id": "P1"}],
                          plan=plan.model_dump(), reflect_count=1,
                          completed_steps=[s.step_id for s in plan.steps])
    state, route = await _run_reflect(state, monkeypatch, [False])
    assert route == "end"
    assert state.reflect_count == 1  # 未再消耗预算
    assert state.harness_report.get("passed") is False  # 失败如实上报


async def test_reflect_chitchat_zero_results_not_retried(monkeypatch):
    plan = await RulePlanner().plan(WorkflowState(intent="chitchat"))
    state = WorkflowState(intent="chitchat", answer="你好呀",
                          plan=plan.model_dump(),
                          completed_steps=[s.step_id for s in plan.steps])
    state, route = await _run_reflect(state, monkeypatch, [True])
    assert route == "end" and state.reflect_count == 0


def test_requeue_step_ids_unique():
    import app.workflow.graph as g

    state = WorkflowState(plan={"steps": [], "max_reflects": 2})
    state.reflect_count = 1
    g._requeue(state, ["response"])
    state.reflect_count = 2
    g._requeue(state, ["retrieval", "response"])
    ids = [s["step_id"] for s in state.plan["steps"]]
    assert len(ids) == len(set(ids)) == 3
