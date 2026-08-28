"""Versioned entity-resolution benchmark (64 cases before catalog-specific additions)."""

from __future__ import annotations


def _cases(values: tuple[str, ...], expected: str, group: str) -> list[dict]:
    return [{"query": value, "expected": expected, "group": group} for value in values]


# These are deliberately phrased as shoppers write them, rather than only copied
# catalog titles.  The focused and visual groups are executed by the evaluator with
# their respective input path once the catalog index exists.
ENTITY_EVAL_CASES: list[dict] = (
    _cases(
        (
            "iphone",
            "iPhone",
            "IPHONE",
            "i phone",
            "苹果手机",
            "爱疯",
            "Apple iPhone",
            "我想买iPhone",
            "帮我找苹果手机",
            "欧米，看看iPhone",
            "想换个爱疯",
            "iphone有哪些",
        ),
        "product_family",
        "iphone_line",
    )
    + _cases(
        (
            "iphone15",
            "iPhone15",
            "iPhone 15",
            "iphone 15",
            "苹果15",
            "苹果 15",
            "爱疯15",
            "apple15",
            "Apple 15",
            "我要15代iphone",
            "15代苹果手机",
            "iPhone十五",
            "iphone15手机",
            "帮我找iPhone 15",
            "欧米推荐苹果15",
            "15系列iPhone",
        ),
        "product_family",
        "iphone_generation",
    )
    + _cases(
        (
            "iphone15pro",
            "iPhone15 Pro",
            "iPhone 15 Pro",
            "iphone 15 pro",
            "苹果15pro",
            "苹果15 Pro",
            "爱疯15pro",
            "apple15pro",
            "iPhone15Pro",
            "15pro苹果手机",
            "iPhone15Pro报价",
            "欧米看看iPhone15Pro",
            "iPhone 15pro",
            "IPHONE15PRO",
            "苹果十五pro",
            "爱疯 15 pro",
        ),
        "exact_product",
        "iphone_model",
    )
    + _cases(
        (
            "iPhone保护壳",
            "iphone手机壳",
            "苹果15充电器",
            "iPhone数据线",
            "iPhone贴膜",
            "iPhone支架",
            "iPhone镜头配件",
            "iPhone充电宝",
        ),
        "no_match",
        "accessory_not_phone",
    )
    + _cases(
        (
            "火星折叠手机Z999",
            "不存在的星际耳机",
            "foo-brand-unknown-2026",
            "我想买一个完全不存在的型号",
        ),
        "no_match",
        "out_of_catalog",
    )
    + [
        {
            "query": "帮我看看这台",
            "expected": "exact_product",
            "group": "visual_entity",
            "visual": {"brand": "Apple", "product_name": "iPhone 15 Pro", "specs": "256GB"},
        },
        {
            "query": "这是什么型号",
            "expected": "exact_product",
            "group": "visual_entity",
            "visual": {"brand": "Apple", "product_name": "iPhone15Pro", "specs": ""},
        },
        {
            "query": "帮我看看这个手机壳",
            "expected": "exact_product",
            "group": "visual_entity",
            "visual": {"brand": "Apple", "product_name": "iPhone 15 Pro", "specs": "256GB"},
        },
        {"query": "iphnoe15pro", "expected": "product_family", "group": "typo_fuzzy_model"},
        {"focused": True, "expected": "exact_product", "group": "focused_product"},
        {"focused": True, "expected": "exact_product", "group": "focused_product"},
        {"focused": True, "expected": "exact_product", "group": "focused_product"},
        {"focused": True, "expected": "exact_product", "group": "focused_product"},
        {"focused": True, "expected": "exact_product", "group": "focused_product"},
        {"focused": True, "expected": "exact_product", "group": "focused_product"},
    ]
)

assert len(ENTITY_EVAL_CASES) >= 60
