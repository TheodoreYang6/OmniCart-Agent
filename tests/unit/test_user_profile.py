"""UserProfileService V2 unit tests — 条目化 + 品类检索。"""
import pytest
from app.services.user_profile_service import UserProfileService


def _svc() -> UserProfileService:
    return UserProfileService()


# ============================================================
# Category Detection
# ============================================================

class TestCategoryDetection:
    def test_phone(self):
        assert _svc().detect_category_from_query("推荐一款手机") == "数码电子"
        assert _svc().detect_category_from_query("买个充电宝") == "数码电子"

    def test_skincare(self):
        assert _svc().detect_category_from_query("保湿精华推荐") == "美妆护肤"
        assert _svc().detect_category_from_query("什么面膜好用") == "美妆护肤"

    def test_no_match(self):
        assert _svc().detect_category_from_query("推荐一下") == ""
        assert _svc().detect_category_from_query("便宜的") == ""

    def test_food_keywords(self):
        assert _svc().detect_category_from_query("我要买吃的") == "食品饮料"
        assert _svc().detect_category_from_query("有什么零食推荐") == "食品饮料"


# ============================================================
# Long-term signal detection
# ============================================================

class TestLongTermSignal:
    def test_remember(self):
        assert _svc().has_long_term_signal("记住，以后都要快充")
        assert _svc().has_long_term_signal("我一直喜欢索尼")

    def test_no_signal(self):
        assert not _svc().has_long_term_signal("推荐一款手机")
        assert not _svc().has_long_term_signal("")

    def test_temporary_exclusion(self):
        assert not _svc().has_long_term_signal("这次要便宜的")

    def test_short_message(self):
        assert not _svc().has_long_term_signal("记住")


# ============================================================
# build_context_hints from entries
# ============================================================

class TestContextHintsFromEntries:
    def test_multi_entries_same_category(self):
        entries = [
            {"brands": ["Apple"], "scenarios": ["出差"], "avoid_tags": ["太重"],
             "must_tags": ["快充"], "category": "数码电子"},
            {"brands": ["Anker"], "must_tags": ["便携"], "category": "数码电子"},
        ]
        ctx = _svc()._build_context_hints_from_entries(entries, "数码电子")
        assert "偏好品牌" in ctx
        assert "Apple" in ctx
        assert "Anker" in ctx
        assert "快充" in ctx
        assert "便携" in ctx
        assert "太重" in ctx
        assert "出差" in ctx

    def test_empty(self):
        assert _svc()._build_context_hints_from_entries([]) == ""

    def test_partial_fields(self):
        entries = [{"brands": ["Sony"], "category": "数码电子"}]
        ctx = _svc()._build_context_hints_from_entries(entries, "数码电子")
        assert "Sony" in ctx
        assert "用户偏好" in ctx
        assert "优先推荐偏好品牌" in ctx


# ============================================================
# Search hints from entries
# ============================================================

class TestSearchHintsFromEntries:
    def test_dedup(self):
        entries = [
            {"must_tags": ["快充", "便携"]},
            {"must_tags": ["快充", "USB-C"]},
        ]
        hints = _svc()._build_search_hints_from_entries(entries)
        assert "快充" in hints
        assert "便携" in hints
        assert "USB-C" in hints
        # 去重
        assert hints.count("快充") == 1

    def test_brands_in_hints(self):
        entries = [{"brands": ["Adidas", "Nike"], "must_tags": []}]
        hints = _svc()._build_search_hints_from_entries(entries)
        assert "Adidas" in hints
        assert "Nike" in hints

    def test_skin_suffix_stripped(self):
        entries = [{"must_tags": ["油皮肤质适用"]}]
        hints = _svc()._build_search_hints_from_entries(entries)
        assert "肤质适用" not in hints
        assert "油皮" in hints


# ============================================================
# Avoid keywords from entries
# ============================================================

class TestAvoidKeywordsFromEntries:
    def test_merge_across_entries(self):
        entries = [
            {"avoid_tags": ["太重"]},
            {"avoid_tags": ["续航短", "太重"]},
        ]
        result = _svc()._get_avoid_keywords_from_entries(entries)
        assert "太重" in result
        assert "续航短" in result
        assert len(result) == 2  # dedup


# ============================================================
# normalize_fields (V2: category singular)
# ============================================================

class TestNormalizeFields:
    def test_categories_to_category(self):
        parsed = {"categories": ["数码电子"], "brands": ["Apple"]}
        result = _svc()._normalize_fields(parsed)
        assert result.get("category") == "数码电子"
        assert "categories" not in result

    def test_skin_type(self):
        parsed = {"skin_type": ["油皮"]}
        result = _svc()._normalize_fields(parsed)
        assert "油皮肤质适用" in result.get("must_tags", [])
        assert result.get("category") == "美妆护肤"

    def test_unknown_to_must_tags(self):
        parsed = {"flavor": ["抹茶"]}
        result = _svc()._normalize_fields(parsed)
        assert "抹茶" in result.get("must_tags", [])


# ============================================================
# JSON extraction
# ============================================================

class TestExtractJson:
    def test_valid(self):
        result = _svc()._extract_json('{"brands": ["Apple"]}')
        assert result == {"brands": ["Apple"]}

    def test_markdown(self):
        result = _svc()._extract_json('```json\n{"brands": ["Sony"]}\n```')
        assert result == {"brands": ["Sony"]}

    def test_trailing_comma(self):
        result = _svc()._extract_json('{"brands": ["Apple",],}')
        assert result is not None

    def test_empty(self):
        assert _svc()._extract_json("") is None
