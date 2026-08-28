"""shopping.display 选品工具与下游同源消费的测试。

这套断言守的是一条不变量：**卡片与答文的候选集必须来自 LLM 显式确认的那一份**。
破坏它就会回到"卡片讲 A/B、回答讲 C/D"的老问题。
"""

from __future__ import annotations

from app.agents.response_agent import ResponseAgent
from app.framework.tools import ToolContext
from app.providers.tools.shopping import DisplayProductsTool
from app.schemas.workflow import WorkflowState


def _state(**kw) -> WorkflowState:
    return WorkflowState(user_query="推荐面霜", **kw)


# ══════════════════════════════════════════════════════════════════════
# 工具本身
# ══════════════════════════════════════════════════════════════════════

async def test_rejects_ids_outside_retrieved_set():
    """防编造：不在 retrieved_products 里的 id 必须被拒绝，且不污染 state。

    这是"同源"的第一道闸 —— LLM 只能从真实召回结果里选，不能凭空造 id。
    """
    state = _state(retrieved_products=[{"product_id": "p1", "title": "A面霜", "brand": "X"}])
    res = await DisplayProductsTool().run(ToolContext(state=state), product_ids=["p9"])
    assert not res.ok
    assert "不在已检索结果里" in res.message
    assert not state.selected_products


async def test_writes_selection_in_given_order():
    """选品顺序必须原样保留 —— 那是 LLM 给出的推荐优先级，卡片顺序据此排。"""
    state = _state(retrieved_products=[
        {"product_id": "p1", "title": "A面霜", "brand": "X"},
        {"product_id": "p2", "title": "B面霜", "brand": "Y"},
        {"product_id": "p3", "title": "C面霜", "brand": "Z"},
    ])
    res = await DisplayProductsTool().run(ToolContext(state=state),
                                          product_ids=["p3", "p1"], reason="更适合干皮")
    assert res.ok
    assert [p["product_id"] for p in state.selected_products] == ["p3", "p1"]
    assert state.selected_reason == "更适合干皮"


async def test_partial_unknown_ids_kept_with_warning():
    """部分 id 无效时保留有效的那些，并在回执里告知 —— 不因一个坏 id 丢掉整次选品。"""
    state = _state(retrieved_products=[{"product_id": "p1", "title": "A面霜", "brand": "X"}])
    res = await DisplayProductsTool().run(ToolContext(state=state), product_ids=["p1", "ghost"])
    assert res.ok
    assert [p["product_id"] for p in state.selected_products] == ["p1"]
    assert "忽略了" in res.message


async def test_empty_ids_rejected():
    state = _state(retrieved_products=[{"product_id": "p1", "title": "A", "brand": "X"}])
    res = await DisplayProductsTool().run(ToolContext(state=state), product_ids=[])
    assert not res.ok and not state.selected_products


async def test_no_state_is_tolerated():
    """脚本直调等无 state 场景不应抛异常（registry.invoke 会把异常转成失败回填）。"""
    res = await DisplayProductsTool().run(ToolContext(), product_ids=["p1"])
    assert not res.ok


# ══════════════════════════════════════════════════════════════════════
# 下游同源消费
# ══════════════════════════════════════════════════════════════════════

def test_context_products_prefers_selection_over_first_n():
    """ResponseAgent 候选集必须优先用选品集。

    ``retrieved_products[:n]`` 的前提是"排过序、前 n 即最优"，这只在 pipeline 路径成立；
    ReAct 路径下它是多次检索的累积，前 n 只是最后一次搜的结果。
    """
    state = _state(
        retrieved_products=[{"product_id": f"r{i}", "title": f"R{i}", "brand": "B"}
                            for i in range(8)],
        selected_products=[{"product_id": "r7", "title": "R7", "brand": "B"}],
    )
    products, _ = ResponseAgent._context_products(state, 5)
    assert [p["product_id"] for p in products] == ["r7"]
    assert state.answer_cited_pids == ["r7"], "引用集必须跟着选品走，卡片置顶依赖它"


def test_context_products_falls_back_when_no_selection():
    """未选品时保持 pipeline 路径的既有行为不变。"""
    state = _state(retrieved_products=[{"product_id": f"r{i}", "title": f"R{i}", "brand": "B"}
                                       for i in range(8)])
    products, _ = ResponseAgent._context_products(state, 3)
    assert [p["product_id"] for p in products] == ["r0", "r1", "r2"]


def test_decisions_filtered_to_selection():
    """决策分要跟着选品裁剪，否则答文会引用未展示商品的评分。"""
    state = _state(
        retrieved_products=[{"product_id": "a", "title": "A", "brand": "X"},
                            {"product_id": "b", "title": "B", "brand": "Y"}],
        selected_products=[{"product_id": "b", "title": "B", "brand": "Y"}],
        decision_results=[{"product_id": "a", "final_score": 0.9},
                          {"product_id": "b", "final_score": 0.7}],
    )
    _, decisions = ResponseAgent._context_products(state, 5)
    assert [d["product_id"] for d in decisions] == ["b"]


# ══════════════════════════════════════════════════════════════════════
# 检索结果文本必须带 id（LLM 能选品的前提）
# ══════════════════════════════════════════════════════════════════════

def test_search_summary_exposes_product_id():
    """shopping.search 的文本行必须带 [product_id]。

    res.data 会被 summarize_result 的 json.dumps(...)[:300] 随机腰斩，
    文本通道是 LLM 唯一能稳定拿到完整 id 的地方；拿不到就无法调 display。
    """
    import inspect

    from app.providers.tools import shopping

    src = inspect.getsource(shopping)
    assert 'f"{i}. [{pid}]' in src, "检索结果文本行丢了 product_id，LLM 将无法选品"
