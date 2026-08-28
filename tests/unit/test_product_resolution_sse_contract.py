from types import SimpleNamespace

from app.api.agent_stream import _focused_comparison_payload, _recommendation_event_payload
from app.schemas.workflow import WorkflowState


def test_product_resolution_fields_are_present_in_recommendation_event():
    state = WorkflowState(
        product_resolution={"match_type": "exact_product", "label": "已锁定：iPhone 15 Pro"},
        retrieval_scope="exact_product",
        resolved_product_ids=["p_1", "p_2"],
        focus_product_id="p_1",
        product_dossiers={
            "p_1": {
                "product_id": "p_1", "title": "iPhone 15 Pro",
                "evidence_status": "证据充分", "information_gaps": [],
            }
        },
    )
    payload = _recommendation_event_payload(state)
    assert payload["product_resolution"]["match_type"] == "exact_product"
    assert payload["retrieval_scope"] == "exact_product"
    assert payload["resolved_product_ids"] == ["p_1", "p_2"]
    assert payload["product_dossier"]["product_id"] == "p_1"
    assert payload["product_dossier"]["evidence_status"] == "证据充分"


def test_focused_comparison_only_includes_same_subcategory_candidates():
    target = SimpleNamespace(
        product_id="p_target", title="目标面霜", brand="欧米", category="美妆护肤",
        sub_category="面霜", base_price=299,
    )
    state = WorkflowState(
        focus_product_id="p_target",
        retrieved_products=[
            {"product_id": "p_target", "title": "目标面霜", "brand": "欧米", "category": "美妆护肤", "sub_category": "面霜", "price": 299},
            {"product_id": "p_alt", "title": "同类面霜", "brand": "测试", "category": "美妆护肤", "sub_category": "面霜", "price": 199},
            {"product_id": "p_other", "title": "不应混入的精华", "brand": "测试", "category": "美妆护肤", "sub_category": "精华", "price": 199},
        ],
        decision_results=[
            {"product_id": "p_target", "recommendation_level": "recommended", "evidence_confidence": 0.8},
            {"product_id": "p_alt", "recommendation_level": "worth_considering", "evidence_confidence": 0.5},
        ],
        product_dossiers={"p_target": {"evidence_status": "证据充分"}},
    )
    alternatives, table, cards = _focused_comparison_payload(state, target)

    assert [item["product_id"] for item in alternatives] == ["p_alt"]
    assert table is not None
    assert table["dimensions"] == ["商品", "价格", "核心特点", "适合场景"]
    assert table["alternative_values"][0][0] == "测试 同类面霜"
    assert table["target_values"][2] == "面霜基础款"
    assert table["alternative_values"][0][3] == "日常护肤"
    assert [item["product_id"] for item in cards] == ["p_target", "p_alt"]
