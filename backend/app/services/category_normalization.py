"""受控商品一级品类的归一化。

品类值常来自模型、视觉识别或旧客户端；它们不能直接成为决策硬约束。
未知值返回 ``None``，让检索保持开放，而不是把所有正确商品误判为不匹配。
"""

from __future__ import annotations

CANONICAL_CATEGORIES = frozenset({
    "数码电子", "美妆护肤", "服饰运动", "食品饮料", "家居用品", "母婴用品", "运动户外", "个护清洁",
})

CATEGORY_ALIASES = {
    "数码": "数码电子", "电子产品": "数码电子",
    "美妆": "美妆护肤", "护肤": "美妆护肤",
    "服饰": "服饰运动", "服装": "服饰运动",
    "食品": "食品饮料", "食品生活": "食品饮料", "食品百货": "食品饮料",
    "家居": "家居用品", "母婴": "母婴用品",
    "户外": "运动户外", "运动": "运动户外",
    "个护": "个护清洁", "清洁": "个护清洁",
}


def normalize_category(category: str | None) -> str | None:
    """映射口语/旧称；不认识的值不应触发品类硬过滤。"""
    value = (category or "").strip()
    if not value:
        return None
    normalized = CATEGORY_ALIASES.get(value, value)
    return normalized if normalized in CANONICAL_CATEGORIES else None
