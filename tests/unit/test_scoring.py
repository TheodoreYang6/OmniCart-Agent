from app.decision.scoring import DecisionScoring
from app.schemas.product import Product, RagKnowledge, ReviewItem


def make_product(product_id="p_digital_001", title="Test 蓝牙耳机",
                 brand="TestBrand", category="数码电子", sub_category="真无线耳机",
                 base_price=199.0, reviews=None):
    reviews = reviews or [
        ReviewItem(nickname="User1", rating=4, content="还不错"),
        ReviewItem(nickname="User2", rating=5, content="很好"),
        ReviewItem(nickname="User3", rating=3, content="一般"),
    ]
    return Product(
        product_id=product_id, title=title, brand=brand,
        category=category, sub_category=sub_category, base_price=base_price,
        rag_knowledge=RagKnowledge(
            marketing_description="一款优质的蓝牙耳机，支持主动降噪，续航长",
            user_reviews=reviews,
        )
    )


def test_score_range():
    scorer = DecisionScoring()
    p = make_product()
    result = scorer.score(p, "蓝牙耳机推荐")
    assert 0.0 <= result.final_score <= 1.0
    assert 0.0 <= result.display_score <= 10.0


def test_budget_fit_perfect():
    scorer = DecisionScoring()
    p = make_product(base_price=100)
    result = scorer.score(p, "100元的蓝牙耳机", budget_max=100)
    assert result.score_breakdown.budget_fit > 0.9


def test_budget_exceeded_lowers_score():
    scorer = DecisionScoring()
    p = make_product(base_price=300)
    result = scorer.score(p, "蓝牙耳机", budget_max=100)
    assert result.score_breakdown.budget_fit < 0.3


def test_expensive_product_risk():
    scorer = DecisionScoring()
    p = make_product(base_price=2500)
    result = scorer.score(p, "高端耳机")
    assert result.score_breakdown.risk_penalty > 0.0


def test_review_confidence():
    scorer = DecisionScoring()
    p = make_product(reviews=[
        ReviewItem(nickname="U1", rating=5, content="完美"),
        ReviewItem(nickname="U2", rating=5, content="超赞"),
        ReviewItem(nickname="U3", rating=4, content="不错"),
    ])
    result = scorer.score(p, "蓝牙耳机")
    assert result.score_breakdown.review_confidence > 0.7


def test_result_has_evidence_ids():
    scorer = DecisionScoring()
    p = make_product()
    result = scorer.score(p, "蓝牙耳机")
    assert len(result.evidence_ids) > 0


def test_scenario_fit():
    scorer = DecisionScoring()
    p = make_product()
    # "蓝牙耳机" appears in the product description, so scenario_fit should be > 0
    result = scorer.score(p, "蓝牙耳机", scenario="commute")
    assert result.score_breakdown.scenario_fit > 0.0
