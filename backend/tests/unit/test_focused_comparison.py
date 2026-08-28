"""问欧米与专用同类对比工作流回归测试。"""

from types import SimpleNamespace

from app.api.agent_stream import (
    _build_focus_analysis,
    _focused_answer,
    _focused_filter_bucket,
    _short_product_name,
)
from app.services.same_category_comparison import (
    _apply_judgement,
    _fallback_verdict,
    select_comparable_products,
)


def _dossier(pid, price=100, avg=4.5, count=10, category="数码电子"):
    return {
        "product_id": pid, "title": f"商品{pid}", "brand": "品牌", "category": category,
        "sub_category": "耳机", "price": price, "price_range": {"min": price, "max": price},
        "marketing_description": "续航很强，兼容主流设备",
        "official_faq": [{"question": "支持哪些设备？", "answer": "兼容主流设备"}],
        "skus": [{"sku_id": "s1", "properties": {"颜色": "黑"}, "price": price}],
        "review_summary": {"avg_rating": avg, "count": count, "positive_count": count, "risk_count": 0},
        "information_gaps": [], "evidence_ids": ["e1"], "evidence_status": "证据充分",
    }


def _product(pid, price, title, *, brand="品牌", description=True):
    knowledge = SimpleNamespace(
        marketing_description="说明" if description else "",
        official_faq=[{"question": "q", "answer": "a"}], user_reviews=[{"rating": 1}],
    )
    return SimpleNamespace(
        product_id=pid, base_price=price, title=title, brand=brand, category="数码电子",
        sub_category="耳机", rag_knowledge=knowledge, skus=[{"sku_id": "s"}],
    )


def test_same_category_selector_dedupes_same_family_and_covers_price_bands():
    target = _product("target", 1000, "Air Pro 降噪耳机")
    same_family = _product("same", 900, "Air Pro 降噪耳机 黑色")
    lower = _product("lower", 650, "Lite 通勤耳机")
    near = _product("near", 1050, "Studio 平衡耳机")
    upper = _product("upper", 1500, "Max 旗舰耳机")

    class Repo:
        def filter_by(self, **_kwargs):
            return [target, same_family, lower, near, upper]

    result = select_comparable_products(Repo(), target)
    ids = [item.product_id for item in result]
    assert "same" not in ids
    assert {"lower", "near", "upper"}.issubset(ids)


def test_model_judgement_is_closed_set_and_never_accepts_unknown_winner():
    comparison = {
        "target": {"product_id": "t", "cautions": [], "suitable_for": ""},
        "alternatives": [{"product_id": "a", "cautions": [], "suitable_for": ""}],
        "verdict": _fallback_verdict([{"price": 100}, {"price": 200}]),
    }
    accepted = _apply_judgement(comparison, {
        "winner_id": "a", "verdict_text": "预算允许时，a 的已标注规格更适合你的使用场景。",
        "reasons": ["规格差异已核对"],
        "items": [
            {"product_id": "t", "choice_reason": "预算优先时先看这款", "caution": "规格资料有限"},
            {"product_id": "a", "choice_reason": "更看重已标注规格时选择", "caution": "以详情为准"},
        ],
    })
    assert accepted is True
    assert comparison["verdict"]["winner_id"] == "a"
    assert comparison["alternatives"][0]["suitable_for"]

    bad = {
        "target": {"product_id": "t", "cautions": [], "suitable_for": ""},
        "alternatives": [{"product_id": "a", "cautions": [], "suitable_for": ""}],
        "verdict": {},
    }
    assert _apply_judgement(bad, {
        "winner_id": "made-up", "verdict_text": "这不是有效结论，必须拒绝。",
        "items": [{"product_id": "t", "choice_reason": "x"}],
    }) is False


def test_apply_judgement_humanizes_product_ids_in_verdict():
    comparison = {
        "target": {"product_id": "p_beauty_007", "brand": "薇诺娜", "title": "保湿特护霜", "cautions": []},
        "alternatives": [{"product_id": "p_beauty_037", "brand": "修丽可", "title": "精华露", "cautions": []}],
    }
    raw = {
        "winner_id": None,
        "verdict_text": "若预算有限选p_beauty_007；若追求保湿选p_beauty_037。",
        "reasons": ["p_beauty_007 价格更低"],
        "items": [
            {"product_id": "p_beauty_007", "choice_reason": "预算有限时更合适", "caution": "注意成分"},
            {"product_id": "p_beauty_037", "choice_reason": "保湿更突出", "caution": ""},
        ],
    }
    assert _apply_judgement(comparison, raw) is True
    verdict_text = comparison["verdict"]["text"]
    assert "p_beauty" not in verdict_text
    assert "薇诺娜" in verdict_text
    assert "修丽可" in verdict_text
    assert all("p_beauty" not in reason for reason in comparison["verdict"]["reasons"])


def test_build_focus_analysis_keeps_rating_and_price_range():
    analysis = _build_focus_analysis(_dossier("p1", price=199))
    assert analysis["product_id"] == "p1"
    assert analysis["rating"]["avg"] == 4.5
    assert analysis["price_range"]["min"] == 199


def test_focused_answer_uses_structured_dossier_without_markdown_or_marketing_claims():
    dossier = _dossier("p1", price=129, avg=3.8, count=5, category="美妆护肤")
    dossier["title"] = "安热沙小金瓶防晒乳SPF50+ PA++++清爽控油版60ml（2024新版）高倍防晒"
    dossier["skus"] = [{"sku_id": "s1", "properties": {"容量": "60ml", "防晒指数": "SPF50+ PA++++"}, "price": 129}]
    product = {"title": dossier["title"], "brand": "安热沙", "price": 129}
    answer = _focused_answer(dossier, product, "这款防晒适合去海边吗？")
    assert "SPF50+ PA++++" in answer
    assert "及时补涂" in answer
    assert "3.8/5" in answer
    assert "**" not in answer
    assert "1.3倍" not in answer
    assert _focused_filter_bucket("这款防晒适合去海边吗？") == "conditional"
    assert _focused_filter_bucket("帮我介绍一下这款防晒") == "primary"
    assert "（" not in _short_product_name(product)
