"""API 层 Prompt 模板 — 对话标题生成 / 商品聚焦分析。

模板常量集中定义，业务代码通过 build_xxx() 组装函数引用。
"""

from __future__ import annotations

# ============================================================
# agent_stream — 对话标题生成
# ============================================================

TITLE_GENERATION_PROMPT = (
    "用8字以内的中文给这段购物对话起个标题，只输出标题：\n"
    "用户：{first_query}\n欧米：{first_answer}"
)


def build_title_prompt(first_query: str, first_answer: str) -> str:
    """渲染标题生成 prompt（query 截 60 字，answer 截 80 字）。"""
    return TITLE_GENERATION_PROMPT.format(
        first_query=first_query[:60], first_answer=first_answer[:80]
    )


# ============================================================
# agent_stream — 「问欧米」商品聚焦分析
# ============================================================

# 品类 → 分析角度
FOCUSED_ANALYSIS_CAT_ANGLES = {
    "数码电子": "参数配置、兼容性、使用场景",
    "美妆护肤": "成分功效、适用肤质、性价比",
    "服饰运动": "材质舒适度、尺码适配、穿搭场景",
    "食品饮料": "口味特点、健康程度、规格划算度",
    "家居用品": "材质安全、实用性、收纳空间适配",
    "母婴用品": "安全性、适用月龄、材质成分",
    "运动户外": "专业性能、耐用度、适用运动场景",
    "个护清洁": "成分温和度、清洁力、适用人群",
}

FOCUSED_ANALYSIS_DEFAULT_ANGLE = "优缺点、性价比、是否值得买"

FOCUSED_ANALYSIS_PROMPT = (
    "顾客在咨询这款商品，请优先重点介绍它：\n"
    "「{title}」— {brand}，¥{price}，{cat}/{sub}\n"
    "参考信息：{review_summary}。{faq_summary}。{sku_summary}。\n"
    "描述：{description}\n"
    "用户问：{message}\n\n"
    "回复要求：\n"
    "1. 先用1-2句热情推荐这款商品，突出它最大的卖点\n"
    "2. 列出2-3个核心优点（结合数据）\n"
    "3. 一句话说适用人群\n"
    "4. 如果数据中有差评/风险项，必须提醒用户注意\n"
    "5. 最后如果检索结果里有同类商品，用一句话提一下作为备选\n"
    "重点始终放在顾客问的这款商品上，备选只是捎带提及。控制在200字以内。"
)


def get_analysis_angle(category: str) -> str:
    """获取品类分析角度（未命中时用默认角度）。"""
    return FOCUSED_ANALYSIS_CAT_ANGLES.get(category, FOCUSED_ANALYSIS_DEFAULT_ANGLE)


def build_focused_analysis_prompt(
    title: str,
    brand: str,
    price: float,
    cat: str,
    sub: str,
    review_summary: str,
    faq_summary: str,
    sku_summary: str,
    description: str,
    message: str,
) -> str:
    """渲染商品聚焦分析 prompt。"""
    return FOCUSED_ANALYSIS_PROMPT.format(
        title=title, brand=brand, price=price, cat=cat, sub=sub,
        review_summary=review_summary, faq_summary=faq_summary,
        sku_summary=sku_summary, description=description, message=message,
    )
