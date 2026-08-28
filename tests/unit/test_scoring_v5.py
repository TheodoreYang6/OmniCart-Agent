from types import SimpleNamespace

from app.agents.decision_agent import DecisionAgent
from app.decision.evidence_metrics import EvidenceScoringHelper
from app.decision.scoring import DecisionScoring
from app.schemas.product import Product, RagKnowledge
from app.schemas.workflow import Constraints


def _product(title="Apple iPhone 15", category="数码电子"):
    return Product(
        product_id="p1", title=title, brand="Apple", category=category,
        sub_category="智能手机", base_price=5999,
        rag_knowledge=RagKnowledge(marketing_description="A17 Pro 芯片，支持 5G"),
    )


def test_raw_reranker_relevance_wins_over_legacy_rank_score():
    helper = EvidenceScoringHelper()
    profile = SimpleNamespace(max_rerank_score=0, max_retrieval_score=0, avg_retrieval_score=0)
    score, source = helper.compute_rag_relevance(
        {"relevance_score": 0.23, "reranker_score": 0.91}, profile
    )
    assert score == 0.23
    assert source == "reranker_relevance"


def test_no_signal_fallback_is_not_promotional_high_score():
    scorer = DecisionScoring()
    iphone = _product()
    irrelevant = scorer._calc_keyword_match(iphone, "敏感肌面霜", 0)
    matching = scorer._calc_keyword_match(iphone, "苹果 iPhone 手机", 0)
    assert irrelevant < 0.45
    assert matching > irrelevant


def test_insufficient_evidence_preserves_match_score_instead_of_clamping_to_45():
    result = DecisionScoring().score_with_evidence(
        product=_product(), query="iPhone 15", force_rag_relevance=0.90,
        evidence_metrics=SimpleNamespace(evidence_confidence=0.10),
    )
    assert result.recommendation_level == "insufficient_evidence"
    assert result.final_score > 0.60


def test_legacy_category_alias_does_not_fail_hard_constraint():
    agent = DecisionAgent()
    constraints = Constraints(category="食品生活")
    product = _product(title="三顿半速溶咖啡", category="食品饮料")
    assert agent._passes_hard_constraints(product, constraints)
