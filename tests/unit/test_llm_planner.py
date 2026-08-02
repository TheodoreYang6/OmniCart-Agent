"""Phase 6-B2 LLM Planner 单测 —— 复杂度探测 / PlanValidator / LLMPlanner / HybridPlanner 降级链。"""

import pytest

from app.framework.orchestration import (
    HybridPlanner,
    LLMPlanner,
    PlanValidator,
)
from app.framework.orchestration.planner import _is_complex, _strip_json_fence
from app.schemas.workflow import WorkflowState

_ALLOWED = {"order.list", "cart.remove", "shopping.search", "shopping.check_inventory"}


# ---- 复杂度探测 ----

def test_is_complex_triggers():
    assert _is_complex("看看我的订单然后推荐个类似的") == (True, "multi_step")
    assert _is_complex("如果有货就帮我下单") == (True, "conditional")
    assert _is_complex("我买过的耳机里哪款适合跑步")[0] is True  # cross_domain
    assert _is_complex("先查库存再给我推荐")[0] is True


def test_is_complex_simple_queries_false():
    for q in ("推荐一款蓝牙耳机", "看看购物车", "对比A和B哪个好", "你好呀", ""):
        assert _is_complex(q)[0] is False, q


# ---- JSON 提取 ----

def test_strip_json_fence():
    assert _strip_json_fence('```json\n{"steps": []}\n```') == {"steps": []}
    assert _strip_json_fence('{"a": 1}') == {"a": 1}
    assert _strip_json_fence("not json") == {}
    assert _strip_json_fence("[1,2]") == {}  # 非 dict 降级


# ---- PlanValidator ----

def _v() -> PlanValidator:
    return PlanValidator(_ALLOWED)


def test_validator_accepts_multi_step_with_tool_and_group():
    raw = {"steps": [
        {"id": "s1", "capability": "tool:order.list", "depends_on": []},
        {"id": "s2", "capability": "retrieval", "depends_on": ["s1"]},
        {"id": "s3", "capability": "reranker", "depends_on": ["s2"], "parallel_group": "g"},
        {"id": "s4", "capability": "evidence_check", "depends_on": ["s2"], "parallel_group": "g"},
        {"id": "s5", "capability": "response", "depends_on": ["s3", "s4"]},
    ], "rationale": "查订单再推荐"}
    plan = _v().validate(raw, "recommend", "multi_step")
    assert plan is not None
    assert plan.meta == {"planner": "llm", "trigger": "multi_step"}
    assert [s.capability for s in plan.steps][-1] == "response"


def test_validator_rejects_unknown_capability():
    assert _v().validate({"steps": [{"id": "s1", "capability": "hack_db"}]}, "r", "t") is None


def test_validator_rejects_restricted_tools():
    for bad in ("tool:order.pay", "tool:cart.add", "tool:not.exists"):
        raw = {"steps": [{"id": "s1", "capability": bad, "depends_on": []},
                         {"id": "s2", "capability": "response", "depends_on": ["s1"]}]}
        assert _v().validate(raw, "r", "t") is None, bad


def test_validator_rejects_forward_dep_and_dup_id():
    fwd = {"steps": [{"id": "s1", "capability": "retrieval", "depends_on": ["s2"]},
                     {"id": "s2", "capability": "response", "depends_on": []}]}
    assert _v().validate(fwd, "r", "t") is None
    dup = {"steps": [{"id": "s1", "capability": "retrieval", "depends_on": []},
                     {"id": "s1", "capability": "response", "depends_on": []}]}
    assert _v().validate(dup, "r", "t") is None


def test_validator_rejects_oversize_and_empty():
    over = {"steps": [{"id": f"s{i}", "capability": "retrieval", "depends_on": []}
                      for i in range(9)]}
    assert _v().validate(over, "r", "t") is None
    assert _v().validate({"steps": []}, "r", "t") is None
    assert _v().validate({}, "r", "t") is None


def test_validator_appends_missing_response():
    raw = {"steps": [{"id": "s1", "capability": "tool:order.list", "depends_on": []}]}
    plan = _v().validate(raw, "r", "t")
    assert plan is not None
    assert plan.steps[-1].capability == "response"
    assert plan.steps[-1].depends_on == ["s1"]


def test_validator_clamps_max_reflects():
    raw = {"steps": [{"id": "s1", "capability": "response", "depends_on": []}],
           "max_reflects": 99}
    assert _v().validate(raw, "r", "t").max_reflects == 2


# ---- LLMPlanner（fake gateway）----

class _FakeGw:
    def __init__(self, response: str, raise_exc: bool = False):
        self._resp, self._raise, self.calls = response, raise_exc, 0

    async def chat(self, capability, prompt, system=""):
        self.calls += 1
        if self._raise:
            raise RuntimeError("boom")
        return self._resp


_GOOD_PLAN = ('{"steps": [{"id": "s1", "capability": "tool:order.list", "depends_on": []},'
              '{"id": "s2", "capability": "response", "depends_on": ["s1"]}],'
              '"rationale": "先查订单再回答"}')


async def test_llm_planner_valid_json(monkeypatch):
    gw = _FakeGw(_GOOD_PLAN)
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    plan = await LLMPlanner().plan_or_none(
        WorkflowState(user_query="看看我的订单然后推荐"), "multi_step")
    assert plan is not None and plan.meta["planner"] == "llm"
    assert [s.capability for s in plan.steps] == ["tool:order.list", "response"]


async def test_llm_planner_invalid_json_returns_none(monkeypatch):
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway",
                        lambda: _FakeGw("我不会输出JSON哦"))
    assert await LLMPlanner().plan_or_none(WorkflowState(user_query="q1"), "t") is None


async def test_llm_planner_exception_returns_none(monkeypatch):
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway",
                        lambda: _FakeGw("", raise_exc=True))
    assert await LLMPlanner().plan_or_none(WorkflowState(user_query="q2"), "t") is None


async def test_llm_planner_process_cache_hits(monkeypatch):
    gw = _FakeGw(_GOOD_PLAN)
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    p = LLMPlanner()
    state = WorkflowState(user_query="看订单再推荐点啥")
    assert await p.plan_or_none(state, "t") is not None
    assert await p.plan_or_none(state, "t") is not None
    assert gw.calls == 1  # 第二次进程缓存命中，不再调 LLM


# ---- HybridPlanner 降级链 ----

async def test_hybrid_flag_off_never_touches_gateway(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_LLM_PLANNER", False)
    gw = _FakeGw(_GOOD_PLAN)
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    plan = await HybridPlanner().plan(WorkflowState(
        intent="recommend", user_query="看看我的订单然后推荐个类似的"))
    assert gw.calls == 0
    assert plan.meta.get("planner") != "llm"  # 规则模板


async def test_hybrid_simple_query_uses_rule(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_LLM_PLANNER", True)
    gw = _FakeGw(_GOOD_PLAN)
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    plan = await HybridPlanner().plan(WorkflowState(intent="recommend", user_query="推荐一款蓝牙耳机"))
    assert gw.calls == 0
    assert [s.capability for s in plan.steps] == [
        "retrieval", "reranker", "evidence_check", "decision", "response"]


async def test_hybrid_llm_failure_falls_back_to_rule(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_LLM_PLANNER", True)
    gw = _FakeGw("垃圾输出")
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    plan = await HybridPlanner().plan(WorkflowState(
        intent="recommend", user_query="看看我的订单然后推荐个类似的"))
    assert gw.calls == 1                       # 触发了 LLM
    assert plan.meta.get("planner") != "llm"   # 但降级到规则
    assert plan.steps[-1].capability == "response"
