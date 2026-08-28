from app.schemas.workflow import WorkflowState
from app.verification.response_guard import ResponseGuard


def _state(answer: str) -> WorkflowState:
    return WorkflowState(
        user_query="想喝低糖饮料",
        answer=answer,
        retrieved_products=[{
            "product_id": "tea", "brand": "东方树叶", "title": "0糖茶", "price": 10,
            "product_facts": [{"fact_key": "nutrition.zero_sugar"}],
        }, {
            "product_id": "snack", "brand": "三只松鼠", "title": "低脂零食", "price": 12,
            "product_facts": [{"fact_key": "nutrition.low_fat"}],
        }],
        primary_product_ids=["tea", "snack"],
        answer_cited_pids=["tea", "snack"],
        alternative_product_ids=[],
        retrieval_groups=[
            {"group_id": "g1", "role": "饮品", "status": "matched", "product_ids": ["tea"]},
            {"group_id": "g2", "role": "零食", "status": "matched", "product_ids": ["snack"]},
        ],
    )


def test_guard_rejects_weight_outcome_claims():
    state = _state("东方树叶0糖茶 ¥10，喝它保证不长胖。三只松鼠低脂零食 ¥12。")
    report = ResponseGuard().check(state)
    assert not report["health_claim_safe"]
    assert not state.harness_report["passed"]


def test_guard_rejects_missing_matched_group_from_delivery():
    state = _state("东方树叶0糖茶 ¥10，适合控糖。")
    state.primary_product_ids = ["tea"]
    state.answer_cited_pids = ["tea"]
    report = ResponseGuard().check(state)
    assert not report["group_coverage"]
