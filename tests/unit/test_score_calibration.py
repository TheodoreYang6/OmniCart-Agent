"""真实匹配等级与正向信号单测。"""

from types import SimpleNamespace

from app.agents.decision_agent import DecisionAgent
from app.decision.scoring import DecisionScoring


def _r(pid: str, final: float, hc: str = "pass") -> dict:
    return {"product_id": pid, "final_score": final, "display_score": round(final * 10, 1),
            "recommendation_level": "", "hard_constraint_status": hc}


# ---- 基于真实分的标签 ----

def test_level_thresholds_use_raw_final_score():
    assert DecisionAgent._level_of(0.80) == "strong_recommend"
    assert DecisionAgent._level_of(0.65) == "recommended"
    assert DecisionAgent._level_of(0.50) == "worth_considering"
    assert DecisionAgent._level_of(0.49) == "cautious"


def test_preferred_brands_only_come_from_structured_memory():
    memories = [
        {"memory_type": "brand", "structured_value": {"brand": "Apple"}},
        {"memory_type": "brand", "structured_value": {"brand": "apple"}},
        {"memory_type": "scenario", "structured_value": {"scenario": "通勤"}},
        {"memory_type": "brand", "structured_value": {"brand": "小米"}},
    ]
    assert DecisionAgent._preferred_brands(memories) == ["Apple", "小米"]


def test_display_score_is_not_a_promotional_calibration():
    """兼容字段保留真实比例，不能将单一候选抬到 9.3。"""
    result = _r("only", 0.72)
    assert result["display_score"] == 7.2


# ---- 好评率 / 风险收紧 ----

def _product(ratings: list[int]):
    reviews = [SimpleNamespace(rating=x, content="c", nickname="n") for x in ratings]
    return SimpleNamespace(
        product_id="p1", title="t", brand="b",
        rag_knowledge=SimpleNamespace(user_reviews=reviews, official_faq=[]),
    )


def test_positive_signal_outputs_good_rate():
    s = DecisionScoring._positive_signal(_product([5, 5, 4, 4, 2]))
    assert "5 条评价" in s and "80% 好评" in s, s


def test_positive_signal_requires_enough_reviews():
    assert DecisionScoring._positive_signal(_product([5, 5])) == ""


def test_positive_signal_hidden_when_rate_low():
    assert DecisionScoring._positive_signal(_product([2, 2, 1, 5])) == ""


def test_risk_no_longer_fires_on_single_bad_review():
    """核心修复：1 条差评不再亮警告（998/1000 商品都有差评，旧规则 100% 亮灯）。"""
    risks = DecisionScoring()._gather_risk_factors(_product([5, 5, 5, 4, 2]))
    assert risks == [], risks


def test_risk_fires_on_two_bad_reviews_with_facts():
    risks = DecisionScoring()._gather_risk_factors(_product([5, 4, 2, 1]))
    assert risks and "2 条差评" in risks[0], risks


def test_risk_fires_on_low_average():
    risks = DecisionScoring()._gather_risk_factors(_product([3, 3, 3]))
    assert "综合评分偏低" in risks
