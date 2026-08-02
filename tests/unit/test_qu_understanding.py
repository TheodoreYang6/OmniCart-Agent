"""QU V2 单测 —— 新意图词表 / 高置信保护 / sub_queries 校验 / gift_profile 透传 / 降级。"""

import pytest

from app.agents.router_agent import (
    RouterAgent,
    _rule_based_parse,
    validate_sub_queries,
)
from app.schemas.workflow import WorkflowState


# ---- 规则词表（LLM 失败时的降级兜底） ----

def test_rule_words_new_intents():
    assert _rule_based_parse("上衣裤子鞋搭配一套")["intent"] == "bundle"
    assert _rule_based_parse("健身装备帮我配齐")["intent"] == "bundle"
    assert _rule_based_parse("上次买的洗发水再来一瓶")["intent"] == "replenish"
    assert _rule_based_parse("咖啡豆回购一包")["intent"] == "replenish"
    assert _rule_based_parse("送女朋友生日礼物")["intent"] == "gift"
    assert _rule_based_parse("降噪和通透模式什么区别")["intent"] == "knowledge"


def test_rule_words_no_false_positive():
    # 单目标多定语不是 bundle；"送货"不是 gift
    assert _rule_based_parse("要个降噪好续航长的耳机")["intent"] == "recommend"
    assert _rule_based_parse("什么时候送货")["intent"] != "gift"
    # 购物车操作优先级最高
    assert _rule_based_parse("成套买好了帮我加入购物车")["intent"] == "shop_action"


# ---- 高置信保护与 LLM 纠正 ----

async def _exec_router(monkeypatch, query: str, llm_result: dict):
    async def fake_qu(q, ctx=""):
        return llm_result

    monkeypatch.setattr("app.agents.router_agent.aunderstand_query", fake_qu)
    state = WorkflowState(user_query=query, user_id="u1")
    return await RouterAgent().execute(state)


async def test_bundle_not_overridden_by_llm(monkeypatch):
    """规则强词表 bundle 不被 LLM 的 recommend 降级（高置信保护）。"""
    state = await _exec_router(monkeypatch, "上衣裤子鞋搭配一套",
                               {"intent": "recommend", "category": "服饰运动"})
    assert state.intent == "bundle"


async def test_replenish_not_overridden_by_llm(monkeypatch):
    state = await _exec_router(monkeypatch, "上次买的洗发水再来一瓶",
                               {"intent": "recommend"})
    assert state.intent == "replenish"


async def test_gift_rule_allows_llm_correction(monkeypatch):
    """gift 词易误判，仅规则默认——LLM 可纠正为 recommend。"""
    state = await _exec_router(monkeypatch, "送女朋友生日礼物挑个口红",
                               {"intent": "recommend", "category": "美妆护肤"})
    assert state.intent == "recommend"


# ---- sub_queries 校验 ----

def test_validate_sub_queries_happy_path():
    out = validate_sub_queries([
        {"role": "上衣", "query": "休闲上衣", "category": "服饰运动", "budget_hint": 280},
        {"role": "鞋", "query": "休闲鞋", "category": "服饰运动", "budget_hint": "240"},
    ])
    assert len(out) == 2
    assert out[0].role == "上衣" and out[0].budget_hint == 280
    assert out[1].budget_hint == 240.0  # 字符串数字被转换


def test_validate_sub_queries_rejects_garbage():
    assert validate_sub_queries("not a list") == []
    assert validate_sub_queries(None) == []
    # 单条视为不拆（清空）
    assert validate_sub_queries([{"role": "a", "query": "x"}]) == []
    # query 空的条目被跳过 → 只剩 1 条 → 清空
    assert validate_sub_queries([{"role": "a", "query": ""}, {"role": "b", "query": "y"}]) == []


def test_validate_sub_queries_caps_and_category():
    raw = [{"role": f"r{i}", "query": f"q{i}", "category": "不存在的品类"} for i in range(8)]
    out = validate_sub_queries(raw)
    assert len(out) == 5  # 超 5 截断
    assert all(s.category is None for s in out)  # 坏 category 置 None
    # budget_hint 脏值置 None
    out2 = validate_sub_queries([
        {"role": "a", "query": "x", "budget_hint": "三百"},
        {"role": "b", "query": "y"},
    ])
    assert out2[0].budget_hint is None


# ---- 写入 state 与降级 ----

async def test_sub_queries_written_to_retrieval_plan(monkeypatch):
    state = await _exec_router(monkeypatch, "上衣裤子鞋搭配一套", {
        "intent": "bundle", "category": "服饰运动",
        "sub_queries": [
            {"role": "上衣", "query": "休闲上衣", "category": "服饰运动"},
            {"role": "裤子", "query": "休闲长裤", "category": "服饰运动"},
            {"role": "鞋", "query": "休闲鞋", "category": "服饰运动"},
        ],
    })
    assert state.intent == "bundle"
    assert [s.role for s in state.retrieval_plan.sub_queries] == ["上衣", "裤子", "鞋"]


async def test_gift_profile_passthrough_and_context(monkeypatch):
    state = await _exec_router(monkeypatch, "送妈妈母亲节礼物", {
        "intent": "gift", "gift_profile": {"recipient": "妈妈", "occasion": "母亲节"},
    })
    assert state.intent == "gift"
    assert state.constraints.gift_profile == {"recipient": "妈妈", "occasion": "母亲节"}
    assert "[送礼场景]" in state.context_prompt and "妈妈" in state.context_prompt


async def test_gift_profile_dropped_for_other_intents(monkeypatch):
    state = await _exec_router(monkeypatch, "推荐个耳机", {
        "intent": "recommend", "gift_profile": {"recipient": "误注入"},
    })
    assert state.constraints.gift_profile is None


async def test_llm_failure_degrades_to_rules(monkeypatch):
    async def boom(q, ctx=""):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.agents.router_agent.aunderstand_query", boom)
    state = WorkflowState(user_query="上衣裤子鞋搭配一套", user_id="u1")
    state = await RouterAgent().execute(state)
    assert state.intent == "bundle"                    # 规则兜底
    assert state.retrieval_plan.sub_queries == []      # 降级 = 现状单查询行为
