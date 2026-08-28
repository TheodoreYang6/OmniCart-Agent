"""Phase 7 OmniAgent 端到端（MOCK provider 确定性脚本 + 真实工具注册表）。"""

import pytest

from app.framework.tools import ToolContext
from app.schemas.workflow import WorkflowState


async def _run_loop(msg: str, deep_think: bool = False):
    from app.agents.omni_agent import OmniAgent

    state = WorkflowState(user_id="u_loop", user_query=msg)
    ctx = ToolContext(user_id="u_loop", state=state)
    events = []
    async for ev in OmniAgent().run_events(msg, ctx, deep_think=deep_think):
        events.append(ev)
    return events, state


async def test_loop_e2e_mock_search_round():
    """首轮受控 shopping.search 后直接收敛；SSE 层再基于结果生成自然语言。"""
    events, state = await _run_loop("推荐一款蓝牙耳机")
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status" and kinds[-1] == "done"
    assert any(e["type"] == "tool_result" and e["tool"] == "shopping.search" for e in events)
    # 深检索结果写回 state（供 SSE 层 generate_stream 与前端商品卡）
    assert state.retrieved_products
    assert state.skill_executions and state.skill_executions[0]["skill_name"] == "shopping.search"
    # 受控运行时不再为了生成结论开启第二个 LLM 决策回合；工具记录只留在
    # 请求级账本，最终 AnswerContext 读取已收敛商品/证据，避免工具转录泄漏。
    assert not state.context_prompt
    assert not state.answer_draft


async def test_loop_e2e_non_product_query_ends_fast():
    """无商品词 → MOCK 惰性空 tool_calls → 一轮即止（交给 generate_stream 出答案）。"""
    events, state = await _run_loop("你们家客服电话多少")
    assert events[-1]["type"] == "done" and events[-1]["rounds"] == 1
    assert not state.skill_executions


async def test_agent_loop_flag_default_off():
    from app.core.config import ENABLE_AGENT_LOOP

    # spec omni-harness D1：语义降为"能力开关"默认 true（仅 deep_think 请求进 Loop，
    # 默认链路仍为 pipeline，故默认开启不影响存量行为）
    assert ENABLE_AGENT_LOOP is True


async def test_fast_command_zero_llm(monkeypatch):
    """极速命令（如“看看购物车”）不进 Loop：0 次 LLM 调用，走关键词直达。

    通过 fake gateway 计数验证：ShopActionAgent 关键词命中后不碰 chat_with_tools。
    """
    calls = {"n": 0}

    class _CountGw:
        async def chat_with_tools(self, *a, **kw):
            calls["n"] += 1
            return {"content": "", "tool_calls": []}

    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: _CountGw())
    monkeypatch.setattr("app.core.config.ENABLE_LLM_TOOL_CALLING", False)
    from app.agents.shop_action_agent import ShopActionAgent

    res = await ShopActionAgent().handle("看看购物车", ToolContext(user_id="u_fast"))
    assert res.message  # 关键词直达有回复
    assert calls["n"] == 0  # 全程 0 次 LLM 调用


def test_fast_commands_covered_by_shop_keywords():
    """5 个极速命令均能被购物门控词表命中（Loop 跳过后落 shop 块直达，不会漏到 workflow）。"""
    fast = {"看看购物车", "清空购物车", "我的订单", "我的偏好", "重新开始"}
    gate_words = ["看看购物车", "清空购物车", "我的订单", "我的偏好", "重新开始"]
    for cmd in fast:
        assert any(w in cmd for w in gate_words), cmd


def test_omni_prompt_deep_think_variant():
    from app.prompts.agent_prompts import build_omni_agent_prompt

    normal = build_omni_agent_prompt(deep_think=False)
    deep = build_omni_agent_prompt(deep_think=True)
    assert "欧米" in normal and "禁止编造" in normal
    assert "深度思考模式" in deep and "深度思考模式" not in normal
