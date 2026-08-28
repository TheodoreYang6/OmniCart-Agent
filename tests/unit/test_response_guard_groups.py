from app.schemas.workflow import WorkflowState
from app.verification.response_guard import ResponseGuard


def test_single_retrieval_group_is_not_compound_coverage_failure():
    state = WorkflowState(
        retrieval_groups=[{"group_id": "main", "status": "matched", "product_ids": ["p1"]}],
        primary_product_ids=["p1"],
    )

    assert ResponseGuard._check_group_coverage(state, [{"product_id": "p1", "brand": "欧米"}], "欧米推荐这款")


def test_compound_group_still_requires_each_group_delivery():
    state = WorkflowState(
        retrieval_groups=[
            {"group_id": "g1", "status": "matched", "product_ids": ["p1"]},
            {"group_id": "g2", "status": "matched", "product_ids": ["p2"]},
        ],
        primary_product_ids=["p1"],
    )

    assert not ResponseGuard._check_group_coverage(state, [{"product_id": "p1", "brand": "欧米"}], "欧米推荐这款")
