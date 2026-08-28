from app.schemas.workflow import WorkflowState
from app.verification.response_guard import ResponseGuard


def test_price_guard_checks_the_third_delivered_product_too():
    products = [
        {"product_id": "p1", "brand": "甲", "title": "甲耳机A100", "price": 100},
        {"product_id": "p2", "brand": "乙", "title": "乙耳机B200", "price": 200},
        {"product_id": "p3", "brand": "丙", "title": "丙耳机C300", "price": 300},
    ]
    state = WorkflowState(retrieved_products=products, primary_product_ids=["p1", "p2", "p3"])

    assert not ResponseGuard()._check_price("甲 A100 ¥100，乙 B200 ¥200，丙 C300 ¥999", products)
