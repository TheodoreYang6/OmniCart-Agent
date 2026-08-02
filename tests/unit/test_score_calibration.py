"""批内校准高分制与正向信号单测（spec: 评分体系与卡片交互优化 §1）。

用户拍板原则：分数尽量高（促单），但必须有区分度且标签口径统一。
实测背景：relevance 透传 reranker 分致全员 8.7-9.2 扎堆，且标签三条件判定
与分数公式两套口径出现"同分不同标"；风险条在 998/1000 商品上 100% 亮灯。
"""

from types import SimpleNamespace

from app.agents.decision_agent import DecisionAgent
from app.decision.scoring import DecisionScoring


def _r(pid: str, final: float, hc: str = "pass") -> dict:
    return {"product_id": pid, "final_score": final, "display_score": round(final * 10, 1),
            "recommendation_level": "", "hard_constraint_status": hc}


# ---- 批内校准 ----

def test_calibrate_spreads_scores_into_high_band():
    """扎堆的原始分校准后落在 [8.0, 9.6] 且拉开区分度。"""
    results = [_r("a", 0.90), _r("b", 0.88), _r("c", 0.87)]
    DecisionAgent._calibrate_batch(results)
    ds = [r["display_score"] for r in results]
    assert ds[0] == 9.6 and ds[-1] == 8.0, ds
    assert max(ds) - min(ds) >= 1.0, f"区分度不足: {ds}"
    assert all(8.0 <= d <= 9.6 for d in ds)


def test_calibrate_keeps_descending_order():
    """校准不得打乱原有降序（原始分越高显示分越高）。"""
    results = [_r("a", 0.95), _r("b", 0.80), _r("c", 0.65), _r("d", 0.55)]
    DecisionAgent._calibrate_batch(results)
    ds = [r["display_score"] for r in results]
    assert ds == sorted(ds, reverse=True), ds


def test_calibrate_all_equal_uses_rank_steps():
    """批内全员同分 → 按位次微阶梯递减，仍可辨。"""
    results = [_r("a", 0.88), _r("b", 0.88), _r("c", 0.88)]
    DecisionAgent._calibrate_batch(results)
    ds = [r["display_score"] for r in results]
    assert len(set(ds)) == 3, f"全同分未拉开: {ds}"
    assert ds == sorted(ds, reverse=True)


def test_calibrate_single_candidate():
    results = [_r("only", 0.72)]
    DecisionAgent._calibrate_batch(results)
    assert results[0]["display_score"] == 9.3
    assert results[0]["recommendation_level"] == "strong_recommend"


def test_calibrate_honest_floor_not_boosted():
    """原始分 <0.5 的不相关商品不得被抬进高分区（促单≠欺骗）。"""
    results = [_r("good", 0.90), _r("bad", 0.30)]
    DecisionAgent._calibrate_batch(results)
    bad = next(r for r in results if r["product_id"] == "bad")
    assert bad["display_score"] <= DecisionAgent._HONEST_CAP, bad
    assert bad["recommendation_level"] == "cautious"


def test_calibrate_skips_hard_constraint_failed():
    """硬约束 fail 的商品保留原低分与 not_recommended，不参与校准。"""
    results = [_r("ok", 0.90), _r("fail", 0.45, hc="failed")]
    results[1]["recommendation_level"] = "not_recommended"
    DecisionAgent._calibrate_batch(results)
    failed = next(r for r in results if r["product_id"] == "fail")
    assert failed["display_score"] == 4.5
    assert failed["recommendation_level"] == "not_recommended"


# ---- 标签单一口径 ----

def test_level_thresholds_and_same_score_same_label():
    assert DecisionAgent._level_of(9.6) == "strong_recommend"
    assert DecisionAgent._level_of(9.2) == "strong_recommend"
    assert DecisionAgent._level_of(9.1) == "recommended"
    assert DecisionAgent._level_of(8.5) == "recommended"
    assert DecisionAgent._level_of(8.4) == "worth_considering"
    assert DecisionAgent._level_of(8.0) == "worth_considering"
    assert DecisionAgent._level_of(7.9) == "cautious"
    # 同分必同标（消灭实测中 8.8 分一个"强烈推荐"一个"值得推荐"）
    assert DecisionAgent._level_of(8.8) == DecisionAgent._level_of(8.8)


def test_calibrated_labels_consistent_with_scores():
    """校准后每条的标签必须与其 display_score 分档严格一致。"""
    results = [_r(f"p{i}", 0.9 - i * 0.05) for i in range(5)]
    DecisionAgent._calibrate_batch(results)
    for r in results:
        assert r["recommendation_level"] == DecisionAgent._level_of(r["display_score"]), r


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
