from app.providers.tools.shopping import _normalize_category


def test_search_tool_normalizes_legacy_category_before_decision_scoring():
    """旧称不能传入 DecisionAgent，否则正确商品会被误判为跨品类。"""
    assert _normalize_category("食品生活") == "食品饮料"
    assert _normalize_category("食品") == "食品饮料"
    assert _normalize_category("美妆") == "美妆护肤"


def test_search_tool_drops_unknown_category_instead_of_creating_false_hard_constraint():
    assert _normalize_category("不存在的品类") is None
