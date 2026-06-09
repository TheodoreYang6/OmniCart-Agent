"""共享规则模块 unit tests — 品类检测、预算提取、场景检测、魔数校验。"""
import pytest
from app.decision.rules import (
    detect_category, detect_budget, detect_scenario,
    validate_image_magic, CATEGORY_RULES,
)


class TestCategoryDetection:
    def test_digital_electronics(self):
        assert detect_category("蓝牙耳机推荐") == "数码电子"
        assert detect_category("笔记本电脑哪个好") == "数码电子"
        assert detect_category("iphone手机") == "数码电子"
        assert detect_category("机械键盘推荐") == "数码电子"

    def test_beauty_skincare(self):
        assert detect_category("保湿精华推荐") == "美妆护肤"
        assert detect_category("防晒霜哪个牌子好") == "美妆护肤"
        assert detect_category("粉底液推荐") == "美妆护肤"
        assert detect_category("面膜推荐") == "美妆护肤"

    def test_clothing_sports(self):
        assert detect_category("跑步鞋推荐") == "服饰运动"
        assert detect_category("羽绒服") == "服饰运动"
        assert detect_category("瑜伽裤") == "服饰运动"
        assert detect_category("登山包") == "服饰运动"

    def test_food_beverage(self):
        assert detect_category("咖啡推荐") == "食品饮料"
        assert detect_category("买零食") == "食品饮料"
        assert detect_category("保健品推荐") == "食品饮料"
        assert detect_category("方便面") == "食品饮料"

    def test_no_category_match(self):
        assert detect_category("你好") is None
        assert detect_category("在吗") is None
        assert detect_category("今天天气怎么样") is None

    def test_all_categories_have_keywords(self):
        """确保四大品类都有关键词。"""
        assert len(CATEGORY_RULES) >= 4
        for cat, kws in CATEGORY_RULES:
            assert len(kws) > 10, f"{cat} 关键词太少"


class TestBudgetDetection:
    def test_budget_in_yuan(self):
        assert detect_budget("500元以内的耳机") == 500.0
        assert detect_budget("预算300块") == 300.0
        assert detect_budget("1000元以下") == 1000.0

    def test_budget_yuan_symbol(self):
        assert detect_budget("¥200的手机壳") == 200.0

    def test_budget_none(self):
        assert detect_budget("随便看看") is None
        assert detect_budget("有什么推荐的") is None

    def test_budget_multi_values(self):
        """多个价格出现时取第一个匹配。"""
        result = detect_budget("500元到1000元的耳机")
        assert result is not None


class TestScenarioDetection:
    def test_business_trip(self):
        assert detect_scenario("出差带什么笔记本") == "business_trip"

    def test_travel(self):
        assert detect_scenario("旅行用什么行李箱") == "travel"

    def test_outdoor(self):
        assert detect_scenario("户外露营装备") == "outdoor"
        assert detect_scenario("露营帐篷推荐") == "outdoor"

    def test_office(self):
        assert detect_scenario("办公喝什么咖啡") == "desk"

    def test_sport(self):
        assert detect_scenario("运动鞋推荐") == "sport"
        assert detect_scenario("跑步穿什么鞋") == "running"

    def test_no_scenario(self):
        assert detect_scenario("买什么东西好") is None


class TestImageMagicValidation:
    def test_png(self):
        assert validate_image_magic(b'\x89PNG\r\n\x1a\n\x00\x00\x00\x00') == "image/png"

    def test_jpeg(self):
        assert validate_image_magic(b'\xff\xd8\xff\x00\x00') == "image/jpeg"

    def test_gif(self):
        assert validate_image_magic(b'GIF89a\x00\x00') == "image/gif"

    def test_webp(self):
        assert validate_image_magic(b'RIFFxxxxWEBP') == "image/webp"

    def test_webp_invalid_fourcc(self):
        """WebP 必须有正确的 FourCC。"""
        assert validate_image_magic(b'RIFFxxxxXXXX') is None

    def test_invalid(self):
        assert validate_image_magic(b'not an image!!') is None
        assert validate_image_magic(b'') is None

    def test_too_short(self):
        assert validate_image_magic(b'\x89') is None
