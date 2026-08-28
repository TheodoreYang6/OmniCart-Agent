"""ReAct 收敛策略：常规模式尽快交付，深度模式也必须有硬上限。"""

from app.prompts.agent_prompts import build_omni_agent_prompt
from app.workflow.react.nodes import guard


def test_react_round_budget_has_non_bypassable_caps(monkeypatch):
    """遗留环境变量再大，也不能把单次对话拖入长工具循环。"""
    monkeypatch.setattr(guard, "AGENT_LOOP_MAX_ROUNDS", 99)
    monkeypatch.setattr(guard, "AGENT_LOOP_DEEP_ROUNDS", 99)

    assert guard.budget_for("standard") == 2
    assert guard.budget_for("max") == 5


def test_react_round_budget_allows_explicitly_lower_deployment_limit(monkeypatch):
    monkeypatch.setattr(guard, "AGENT_LOOP_MAX_ROUNDS", 1)
    monkeypatch.setattr(guard, "AGENT_LOOP_DEEP_ROUNDS", 3)

    assert guard.budget_for("standard") == 1
    assert guard.budget_for("max") == 3


def test_prompt_tells_agent_to_stop_once_answer_material_is_available():
    normal = build_omni_agent_prompt()
    deep = build_omni_agent_prompt(deep_think=True)

    assert "一旦已拿到足够的可输出语料，就立即停止调工具" in normal
    assert "不要为了展示卡片再调用它" in normal
    assert "立刻收敛并回答" in deep
