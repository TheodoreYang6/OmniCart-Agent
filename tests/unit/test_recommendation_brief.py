from app.schemas.workflow import WorkflowState
from app.services.recommendation_brief import build_recommendation_brief


def _product(index: int) -> dict:
    return {"product_id": f"p{index}", "title": f"商品{index}", "brand": "欧米", "price": 100 + index}


def _decision(index: int, score: float) -> dict:
    return {
        "product_id": f"p{index}", "final_score": score,
        "recommendation_level": "recommended", "evidence_confidence": 0.8,
        "recommendation_reason": f"原因{index}", "risk_factors": [],
    }


def test_brief_locks_three_primary_and_six_alternatives():
    state = WorkflowState(
        retrieved_products=[_product(i) for i in range(12)],
        decision_results=[_decision(i, 0.9 - i * 0.03) for i in range(12)],
        sufficiency_report={"sufficient": True},
    )

    primary, alternatives = build_recommendation_brief(state)

    assert [p["product_id"] for p in primary] == ["p0", "p1", "p2"]
    assert len(alternatives) == 6
    assert set(state.primary_product_ids).isdisjoint(state.alternative_product_ids)
    assert state.answer_cited_pids == state.primary_product_ids
    assert all(d["match_label"] for d in state.decision_results)
    assert all(d["evidence_label"] == "证据充分" for d in state.decision_results)


def test_explicit_react_selection_has_priority():
    state = WorkflowState(
        retrieved_products=[_product(i) for i in range(5)],
        decision_results=[_decision(i, 0.9 - i * 0.05) for i in range(5)],
        selected_products=[_product(4), _product(3)],
    )

    primary, _ = build_recommendation_brief(state)

    assert [p["product_id"] for p in primary[:2]] == ["p4", "p3"]


def test_grouped_brief_reserves_one_primary_per_matched_group():
    state = WorkflowState(
        retrieved_products=[_product(i) for i in range(4)],
        decision_results=[_decision(0, 0.99), _decision(1, 0.95), _decision(2, 0.70), _decision(3, 0.65)],
        retrieval_groups=[
            {"group_id": "g1", "role": "零食", "status": "matched", "product_ids": ["p0", "p1"]},
            {"group_id": "g2", "role": "饮品", "status": "matched", "product_ids": ["p2", "p3"]},
        ],
    )
    primary, _ = build_recommendation_brief(state)
    assert {"p0", "p2"}.issubset({p["product_id"] for p in primary})


def test_grouped_brief_never_loses_or_duplicates_candidates_when_reserving_groups():
    state = WorkflowState(
        retrieved_products=[_product(i) for i in range(5)],
        decision_results=[_decision(i, 0.99 - i * 0.05) for i in range(5)],
        # Group representatives occur later in the original recall order but
        # must still be selected, without dropping p0/p1 from alternatives.
        retrieval_groups=[
            {"group_id": "g1", "role": "零食", "status": "matched", "product_ids": ["p2"]},
            {"group_id": "g2", "role": "饮品", "status": "matched", "product_ids": ["p3"]},
        ],
    )
    primary, alternatives = build_recommendation_brief(state)
    primary_ids = [p["product_id"] for p in primary]
    alternative_ids = [p["product_id"] for p in alternatives]
    assert {"p2", "p3"}.issubset(primary_ids)
    assert set(primary_ids) | set(alternative_ids) == {"p0", "p1", "p2", "p3", "p4"}
    assert not set(primary_ids) & set(alternative_ids)


def test_brief_uses_verdict_not_numeric_score_for_user_label():
    state = WorkflowState(
        retrieved_products=[{**_product(0), "filter_bucket": "primary", "evidence_types": ["facts"]}],
        decision_results=[{
            **_decision(0, 0.45), "recommendation_level": "cautious",
        }],
        structured_retrieval_report={"version": "v9"},
    )
    build_recommendation_brief(state)
    assert state.recommendation_brief[0]["match_label"] == "高度匹配"


def test_v9_multi_target_keeps_only_one_primary_per_matched_group():
    """饮品缺失时不能把第二张零食卡伪装成又一个主目标答案。"""
    products = [
        {**_product(0), "filter_bucket": "primary", "evidence_types": ["facts"]},
        {**_product(1), "filter_bucket": "primary", "evidence_types": ["facts"]},
        {**_product(2), "filter_bucket": "primary", "evidence_types": ["facts"]},
    ]
    state = WorkflowState(
        retrieved_products=products,
        decision_results=[_decision(i, 0.9 - i * 0.05) for i in range(3)],
        structured_retrieval_report={"version": "v9"},
        retrieval_groups=[
            {"group_id": "plan:1", "role": "零食", "status": "matched", "product_ids": ["p0", "p1"]},
            {"group_id": "plan:2", "role": "饮品", "status": "missing", "product_ids": []},
        ],
    )
    primary, alternatives = build_recommendation_brief(state)
    assert [p["product_id"] for p in primary] == ["p0"]
    assert [p["product_id"] for p in alternatives] == ["p1", "p2"]


def test_v9_primary_cards_do_not_repeat_the_same_model_family():
    products = [
        {"product_id": "w30", "brand": "漫步者", "title": "W30真无线降噪耳机蓝牙5.3", "price": 299,
         "filter_bucket": "primary", "evidence_types": ["facts"]},
        {"product_id": "redmi_12", "brand": "小米", "title": "Redmi Buds 5 Pro真无线降噪耳机12mm动圈", "price": 299,
         "filter_bucket": "primary", "evidence_types": ["facts"]},
        {"product_id": "redmi_10", "brand": "小米", "title": "Redmi Buds 5 Pro真无线降噪耳机10mm双磁动圈", "price": 299,
         "filter_bucket": "primary", "evidence_types": ["facts"]},
    ]
    state = WorkflowState(
        retrieved_products=products,
        decision_results=[
            {"product_id": p["product_id"], "recommendation_level": "recommended", "evidence_confidence": 0.8}
            for p in products
        ],
        structured_retrieval_report={"version": "v9"},
    )

    primary, alternatives = build_recommendation_brief(state)

    assert [p["product_id"] for p in primary] == ["w30", "redmi_12"]
    assert [p["product_id"] for p in alternatives] == ["redmi_10"]
