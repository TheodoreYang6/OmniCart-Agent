"""SSE 出口载荷瘦身单测（spec: SSE载荷瘦身优化 §4）。

锁住三点：商品卡剔除 rag_knowledge 且保留展示字段、证据裁剪（过滤+截断+上限）、
瘦身不改 state 原对象（出口序列化隔离）。
"""

from app.api.agent_stream import (
    _CARD_KEEP,
    _DESC_MAX,
    _EVIDENCE_CONTENT_MAX,
    _EVIDENCE_MAX,
    _slim_evidence,
    _slim_products,
)


def _card(pid="p1", **extra):
    base = {
        "product_id": pid,
        "title": "薇诺娜舒敏保湿修红面膜",
        "brand": "薇诺娜",
        "category": "美妆护肤",
        "sub_category": "面膜",
        "price": 128.0,
        "image_urls": ["/img/p1.jpg"],
        "skus": [{"sku_id": "s1", "price": 128.0}],
        "description": "面膜" * 200,  # 400 字，超 _DESC_MAX
        "score": 0.9,
        "evidence_ids": ["E-1"],
        "rag_knowledge": {"official_faq": [{"q": "x", "a": "y"}] * 20,
                          "user_reviews": [{"r": "好"}] * 30},  # 大冗余
        "reranker_score": 0.88,
        "avg_rating": 4.7,
        "variant_count": 2,
    }
    base.update(extra)
    return base


def test_slim_products_drops_rag_knowledge():
    """rag_knowledge 必须被剔除（前端零消费，最大冗余）。"""
    out = _slim_products([_card()])
    assert "rag_knowledge" not in out[0]


def test_slim_products_keeps_display_fields():
    """前端商品卡与推理面板读取的字段全部保留。"""
    out = _slim_products([_card()])[0]
    for k in ("product_id", "title", "brand", "price", "image_urls", "skus",
              "avg_rating", "variant_count", "reranker_score", "evidence_ids", "score"):
        assert k in out, f"展示字段被误删: {k}"


def test_slim_products_truncates_description():
    out = _slim_products([_card()])[0]
    assert len(out["description"]) == _DESC_MAX


def test_slim_products_does_not_mutate_input():
    """瘦身返回新 dict，不得改动 state 原对象（rag_knowledge 仍在原对象上）。"""
    original = _card()
    _slim_products([original])
    assert "rag_knowledge" in original, "原始 state 对象被污染"
    assert len(original["description"]) == 400


def test_slim_products_only_whitelist_fields():
    out = _slim_products([_card(extra_noise="x", another="y")])[0]
    assert set(out.keys()) <= _CARD_KEEP


def test_slim_products_passthrough_non_dict():
    assert _slim_products(["raw", 123]) == ["raw", 123]


def _ev(pid, i=0, content="补水" * 200):
    return {
        "evidence_id": f"E-{pid}-{i}",
        "source_type": "text_retrieval",
        "source_id": pid,
        "product_id": pid,
        "confidence": 0.6145,
        "content": content,
        "modality": "text",
        "extra_field": "should_be_dropped",
    }


def test_slim_evidence_truncates_content():
    out = _slim_evidence([_ev("p1")], ["p1"], [{"product_id": "p1"}])
    assert len(out[0]["content"]) == _EVIDENCE_CONTENT_MAX


def test_slim_evidence_filters_by_display_pids():
    """不在展示集内的证据被过滤（p2 不在引用集也不在下发商品里）。"""
    evs = [_ev("p1"), _ev("p2")]
    out = _slim_evidence(evs, ["p1"], [{"product_id": "p1"}])
    assert all(e["product_id"] == "p1" for e in out)


def test_slim_evidence_caps_count():
    evs = [_ev("p1", i) for i in range(50)]
    out = _slim_evidence(evs, ["p1"], [{"product_id": "p1"}])
    assert len(out) <= _EVIDENCE_MAX


def test_slim_evidence_keeps_generic_no_pid():
    """无 product_id 的通用证据保留。"""
    generic = {"evidence_id": "G-1", "source_type": "policy", "content": "包邮"}
    out = _slim_evidence([generic], ["p1"], [{"product_id": "p1"}])
    assert len(out) == 1


def test_slim_evidence_keeps_confidence():
    """confidence 必须保留（前端 `e.confidence * 100` 展示可信度，漏保留出 NaN%）。"""
    out = _slim_evidence([_ev("p1")], ["p1"], [{"product_id": "p1"}])
    assert out[0]["confidence"] == 0.6145


def test_slim_evidence_only_whitelist_fields():
    out = _slim_evidence([_ev("p1")], ["p1"], [{"product_id": "p1"}])
    assert set(out[0].keys()) == {"evidence_id", "source_type", "source_id",
                                  "product_id", "confidence", "content"}


def test_active_reranker_name_matches_use_bge():
    """日志模型名与实际生效模型一致（P2 修复）。"""
    from app.model_gateway import local_backend as lb

    name = lb.active_reranker_name()
    assert name == ("bge-reranker-v2-m3" if lb._use_bge() else "Qwen3-Reranker-0.6B")
