"""QU V2 multi_query_retrieval 单测 —— 分组并行 / 合并去重 / 钉顶 / 缺货声明 / 退化。"""

import pytest

from app.schemas.workflow import SubQuery, WorkflowState


def _state(sub_queries):
    st = WorkflowState(user_query="上衣裤子鞋搭一套", intent="bundle", user_id="u1")
    st.retrieval_plan.sub_queries = sub_queries
    st.retrieval_plan.top_k = 12
    return st


def _fake_retrieval(products_by_query):
    async def fake(sub):
        prods = products_by_query.get(sub.user_query, [])
        sub.retrieved_products = [dict(p) for p in prods]
        sub.evidence_list = [{"product_id": p["product_id"], "text": f"{p['product_id']}好评"}
                             for p in prods]
        return sub
    return fake


async def test_three_groups_interleave_dedupe_and_roles(monkeypatch):
    import app.workflow.graph as g

    fake = _fake_retrieval({
        "休闲上衣": [{"product_id": "T1", "title": "上衣A"}, {"product_id": "T2", "title": "上衣B"}],
        "休闲长裤": [{"product_id": "P1", "title": "裤A"}, {"product_id": "T1", "title": "上衣A"}],  # T1 重复
        "休闲鞋": [{"product_id": "S1", "title": "鞋A"}],
    })
    monkeypatch.setattr(g, "_node_retrieval", fake)
    st = _state([SubQuery(role="上衣", query="休闲上衣"),
                 SubQuery(role="裤子", query="休闲长裤"),
                 SubQuery(role="鞋", query="休闲鞋")])
    st = await g._node_multi_query_retrieval(st)

    pids = [p["product_id"] for p in st.retrieved_products]
    # 交替合并 + 去重（T1 只出现一次）后本为 [T1,P1,S1,T2]（4 个），
    # 网格修整（trim_for_grid：末行落单砂尾）再去掉最低优先级的 T2 ——
    # 各组 top1 均在前三，组覆盖不受影响
    assert pids == ["T1", "P1", "S1"]
    roles = {p["product_id"]: p["group_role"] for p in st.retrieved_products}
    assert roles["T1"] == "上衣" and roles["P1"] == "裤子" and roles["S1"] == "鞋"
    assert "multi_query_retrieval_ms" in st.timing


async def test_group_top1_pinned(monkeypatch):
    import app.workflow.graph as g

    fake = _fake_retrieval({
        "休闲上衣": [{"product_id": "T1", "title": "上衣A"}],
        "休闲鞋": [{"product_id": "S1", "title": "鞋A"}],
    })
    monkeypatch.setattr(g, "_node_retrieval", fake)
    st = _state([SubQuery(role="上衣", query="休闲上衣"), SubQuery(role="鞋", query="休闲鞋")])
    st = await g._node_multi_query_retrieval(st)

    assert set(st.visual_matched_pids) >= {"T1", "S1"}  # 每组 top1 钉顶
    for p in st.retrieved_products:
        if p["product_id"] in ("T1", "S1"):
            assert p["reranker_score"] >= 0.95


async def test_missing_group_annotated(monkeypatch):
    import app.workflow.graph as g

    fake = _fake_retrieval({
        "休闲上衣": [{"product_id": "T1", "title": "上衣A"}],
        "限量鞋": [],  # 缺货组
    })
    monkeypatch.setattr(g, "_node_retrieval", fake)
    st = _state([SubQuery(role="上衣", query="休闲上衣"), SubQuery(role="鞋", query="限量鞋")])
    st = await g._node_multi_query_retrieval(st)

    assert "[分组检索]" in st.context_prompt
    assert "上衣:1件" in st.context_prompt and "鞋:0件" in st.context_prompt
    assert "「鞋」未找到符合条件的商品" in st.context_prompt
    assert "回答时须如实说明" in st.context_prompt


async def test_less_than_two_groups_falls_back(monkeypatch):
    import app.workflow.graph as g

    called = {"n": 0}

    async def sentinel(state):
        called["n"] += 1
        return state

    monkeypatch.setattr(g, "_node_retrieval", sentinel)
    st = _state([SubQuery(role="上衣", query="休闲上衣")])  # 仅 1 条 → 退化单路
    await g._node_multi_query_retrieval(st)
    assert called["n"] == 1


async def test_group_exception_counts_zero_and_continues(monkeypatch):
    import app.workflow.graph as g

    async def flaky(sub):
        if sub.user_query == "坏路":
            raise RuntimeError("boom")
        sub.retrieved_products = [{"product_id": "OK1", "title": "ok"}]
        sub.evidence_list = []
        return sub

    monkeypatch.setattr(g, "_node_retrieval", flaky)
    st = _state([SubQuery(role="好", query="好路"), SubQuery(role="坏", query="坏路")])
    st = await g._node_multi_query_retrieval(st)

    assert [p["product_id"] for p in st.retrieved_products] == ["OK1"]
    assert "坏:0件" in st.context_prompt  # 异常组按 0 命中如实声明
