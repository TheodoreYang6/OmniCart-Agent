from app.schemas.workflow import Constraints, WorkflowState
from app.services.recommendation_score import build_recommendation_score
from app.agents.decision_agent import DecisionAgent


def _product(**extra):
    product = {
        "product_id": "p1", "title": "通勤降噪耳机", "brand": "欧米", "category": "数码电子",
        "price": 399, "filter_bucket": "primary", "evidence_types": ["facts", "faq", "review"],
        "product_facts": [{"fact_key": "降噪", "value": "支持", "verified": True}],
        "matched_chunks": [
            {"payload": {"chunk_type": "facts", "text": "支持主动降噪"}},
            {"payload": {"chunk_type": "faq", "text": "保修说明"}},
            {"payload": {"chunk_type": "review", "text": "地铁通勤降噪好"}},
        ],
    }
    product.update(extra)
    return product


def test_display_score_is_deterministic_and_never_reads_rerank_score():
    constraints = Constraints(category="数码电子", budget_max=500)
    first = build_recommendation_score(_product(relevance_score=0.01), constraints)
    second = build_recommendation_score(_product(relevance_score=0.99, chunk_aggregate_score=999), constraints)

    assert first == second
    assert first["score"] >= 82
    assert first["match_label"] == "高度匹配"
    assert [item["label"] for item in first["dimensions"]] == ["需求契合", "预算适配", "资料完整"]


def test_over_budget_product_is_capped_and_not_recommended():
    score = build_recommendation_score(_product(price=799), Constraints(budget_max=500))

    assert score["score"] <= 39
    assert score["recommendation_level"] == "not_recommended"
    assert score["dimensions"][1]["detail"] == "超出本次预算"


async def test_v9_decision_agent_does_not_emit_legacy_scores():
    state = WorkflowState(
        retrieved_products=[_product()],
        constraints=Constraints(category="数码电子", budget_max=500),
        structured_retrieval_report={"version": "v9"},
    )

    await DecisionAgent().execute(state)

    decision = state.decision_results[0]
    assert decision["recommendation_score"]["version"] == "omi_recommendation_v1"
    assert "final_score" not in decision
    assert "display_score" not in decision


async def test_exact_product_analysis_uses_the_same_v9_score_contract():
    state = WorkflowState(
        retrieved_products=[_product()],
        constraints=Constraints(category="数码电子", budget_max=500),
        retrieval_scope="exact_product",
        resolved_product_ids=["p1"],
    )

    await DecisionAgent().execute(state)

    decision = state.decision_results[0]
    assert decision["recommendation_score"]["version"] == "omi_recommendation_v1"
    assert decision["recommendation_score"]["score"] >= 82
    assert decision["recommendation_level"] == "strong_recommend"
    assert "final_score" not in decision
