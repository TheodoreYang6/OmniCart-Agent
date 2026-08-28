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

# 品类 → 商品属性维度（对比事实表与卡片共用）。
CATEGORY_DIMENSIONS = {
    "数码电子": ["价格", "续航", "兼容性", "适用场景"],
    "美妆护肤": ["价格", "成分功效", "适用肤质", "性价比"],
    "服饰运动": ["价格", "材质", "尺码适配", "穿搭场景"],
    "食品饮料": ["价格", "口味", "健康程度", "规格划算度"],
    "家居用品": ["价格", "材质安全", "实用性", "空间适配"],
    "母婴用品": ["价格", "安全性", "适用月龄", "材质成分"],
    "运动户外": ["价格", "专业性能", "耐用度", "适用运动"],
    "个护清洁": ["价格", "成分温和度", "清洁力", "适用人群"],
}

CATEGORY_DIMENSIONS_DEFAULT = ["价格", "核心卖点", "适用人群"]

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


COMPARISON_PROMPT = (
    "下面是同一品类的商品对比事实表。卡片、结论和你的回答必须完全一致，"
    "只能引用表中出现的商品、维度和事实，不要编造表外的数字或卖点：\n"
    "{comparison_text}\n\n"
    "请写一段 180 字以内的导购结论：\n"
    "1. 按卡片顺序简要说明每款的核心差异；\n"
    "2. 结论必须与上面的 verdict 完全一致；\n"
    "3. 直接输出正文，不使用 Markdown 标题或列表符号。"
)


def _comparison_item_text(label: str, item: dict, dimensions: list[str]) -> str:
    price_range = item.get("price_range") or {}
    price_min = price_range.get("min", item.get("price", 0))
    price_max = price_range.get("max", item.get("price", 0))
    attributes = item.get("attributes") or {}
    bits = [f"{label}：{item.get('brand', '')} {item.get('title', '')}"]
    bits.append(f"价格：¥{item.get('price', 0)}（¥{price_min}-¥{price_max}）")
    for dim in dimensions:
        value = attributes.get(dim)
        if value:
            bits.append(f"{dim}：{value}")
    if item.get("highlights"):
        bits.append("卖点：" + "、".join(item["highlights"]))
    if item.get("cautions"):
        bits.append("注意：" + "、".join(item["cautions"]))
    if item.get("suitable_for"):
        bits.append("适合人群：" + item["suitable_for"])
    return "；".join(bits)


def build_comparison_prompt(comparison: dict) -> str:
    """把结构化对比事实表渲染成回答模型的 prompt。"""
    dimensions = list(comparison.get("dimensions") or [])
    lines = [
        _comparison_item_text("目标商品", comparison.get("target") or {}, dimensions),
    ]
    for index, alt in enumerate(comparison.get("alternatives") or [], start=1):
        lines.append(_comparison_item_text(f"备选{index}", alt, dimensions))
    verdict = comparison.get("verdict") or {}
    lines.append("结论：" + str(verdict.get("text") or ""))
    return COMPARISON_PROMPT.format(comparison_text="\n".join(lines))


COMPARISON_RESPONSE_SYSTEM = """你是欧米。请依据已经完成的同类对比裁决，写一段自然、简洁、能帮助用户下决定的中文。

必须遵守：
1. 只引用输入对比表中的商品、价格、属性、资料状态和结论；没有资料时坦诚说“资料有限”，不猜测。
2. 不要逐字复述超长商品标题；每件用品牌加短名称即可。
3. 不要说“综合评分最高”“算法”“候选”“检索”“工具”，也不要输出 Markdown、星号、标题或列表符号。
4. 先点出最关键的选择分界，再说明当前商品适合什么情况；若没有绝对赢家，明确给出条件化建议。
5. 控制在 160 字以内，语气像懂购物的朋友，不要重复猫咪口头禅。
"""


def build_comparison_response_prompt(comparison: dict, user_query: str) -> str:
    """给最终回答模型的唯一对比事实投影。

    这里不传营销长文或工具转录，避免模型把模糊描述扩大成产品承诺。
    """
    dimensions = list(comparison.get("dimensions") or [])
    lines = [_comparison_item_text("当前商品", comparison.get("target") or {}, dimensions)]
    for index, item in enumerate(comparison.get("alternatives") or [], start=1):
        lines.append(_comparison_item_text(f"同类备选{index}", item, dimensions))
    verdict = comparison.get("verdict") or {}
    lines.append("已核对的选购结论：" + str(verdict.get("text") or ""))
    if verdict.get("reasons"):
        lines.append("结论依据：" + "、".join(str(item) for item in verdict["reasons"]))
    return f"用户请求：{user_query}\n对比表：\n" + "\n".join(lines)


def build_order_summary_prompt(shop_card: dict) -> str:
    """把下单预览/成功卡片渲染成接地 LLM prompt，禁止编造。"""
    kind = shop_card.get("kind")
    payload = shop_card.get("payload") or {}
    items = payload.get("items") or []
    total = payload.get("total", 0)
    item_lines = "\n".join(
        f"- {it.get('brand', '')} {it.get('title', '')} x{it.get('quantity', 1)} "
        f"¥{float(it.get('price', 0) or 0) * int(it.get('quantity', 1) or 1):.0f}"
        for it in items
    )
    if kind == "order_preview":
        address = payload.get("address") or {}
        has_address = bool(address)
        address_line = (
            f"收货地址：{address.get('name', '')} {address.get('phone', '')} "
            f"{address.get('province', '')}{address.get('city', '')}"
            f"{address.get('district', '')} {address.get('detail', '')}"
            if has_address else "尚未填写收货地址"
        )
        return (
            "你是购物助手，请根据下面的订单预览信息，用自然、亲切、不超过 100 字的中文提醒用户确认下单；"
            "只引用下面给出的商品、金额和地址，不要编造或补充其他信息：\n"
            f"商品：\n{item_lines}\n合计：¥{float(total):.0f}\n{address_line}"
        )
    if kind == "order_created":
        order_id = payload.get("order_id", "")
        eta = payload.get("eta", "2-3天")
        return (
            "你是购物助手，请根据下面的下单结果，用自然、亲切、不超过 100 字的中文告诉用户下单成功；"
            "只引用下面给出的订单号、件数、金额和送达时间，不要编造：\n"
            f"订单号：{order_id}\n商品：\n{item_lines}\n"
            f"合计：¥{float(total):.0f}\n预计送达：{eta}"
        )
    return "请用一句自然的中文回复用户。"


def build_shop_summary_prompt(shop_card: dict) -> str:
    """按 shop_card.kind 生成接地 LLM prompt（购物车/规格/订单）。"""
    kind = shop_card.get("kind")
    if kind in {"order_preview", "order_created"}:
        return build_order_summary_prompt(shop_card)
    payload = shop_card.get("payload") or {}
    if kind == "cart_summary":
        items = payload.get("items") or []
        total = payload.get("total", 0)
        count = payload.get("count", len(items))
        item_lines = "\n".join(
            f"- {it.get('brand', '')} {it.get('title', '')} x{it.get('quantity', 1)}"
            for it in items
        )
        return (
            "你是购物助手欧米。请根据下面的购物车摘要，用一句自然、亲切、不超过 60 字的中文告诉用户当前购物车情况；"
            "只引用给定商品与金额，不要编造：\n"
            f"商品：\n{item_lines}\n合计：¥{float(total):.0f}（{count} 件）"
        )
    if kind == "sku_picker":
        skus = payload.get("skus") or []
        sku_lines = "、".join(
            f"{s.get('label', '')}（¥{float(s.get('price', 0)):.0f}）" for s in skus
        )
        return (
            "你是购物助手欧米。请用一句自然、不超过 40 字的中文请用户选择规格；"
            f"可选规格：{sku_lines}"
        )
    return "请用一句自然的中文回复用户。"
