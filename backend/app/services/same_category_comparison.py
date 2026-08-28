"""受控的同类商品对比工作流。

这不是通用推荐的一个展示分支。用户从「横向对比」进入时已经锁定了
一件商品，真正需要的是：找出少量可比、彼此有差异的备选，再在闭集事实
内判断各自适合什么情况。这里刻意不使用评价均值来选“赢家”，也不允许
模型写入候选集之外的商品或事实。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable
from typing import Any

from app.model_gateway.gateway import get_model_gateway
from app.prompts.api_prompts import CATEGORY_DIMENSIONS, CATEGORY_DIMENSIONS_DEFAULT
from app.providers.tools.shopping import build_product_dossier

_COMPARISON_JUDGE_SYSTEM = """你是欧米的同类商品对比裁决器。你的任务不是推荐最热门的商品，而是在给定的、已经可追溯的商品事实中，帮助用户看懂差异。

严格规则：
1. 只能使用输入中给出的商品，不得补充商品、价格、规格、功效、评价结论或不存在的维度；在 verdict_text / choice_reason / caution 中提及商品时只能用“品牌+标题”的简称，严禁使用 product_id / p_xxx 编号。
2. 没有一个商品对所有人都更好时，winner_id 必须为 null；不要用评价数量或星级替代用户需求。
3. 商品资料缺失时，只能写“该项资料有限/以详情为准”，不能猜测。
4. verdict_text 说明如何选择，必须是条件化结论；item 的 choice_reason 只写该商品与其他候选的可见差异和适合情形。
5. 输出严格 JSON，不要 Markdown，不要解释过程：
{
  "winner_id": "候选中的 product_id 或 null",
  "verdict_text": "不超过70字的选购结论",
  "reasons": ["不超过22字的选择依据，最多3条"],
  "items": [
    {"product_id":"...", "choice_reason":"不超过42字", "caution":"不超过32字"}
  ]
}
"""


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _short_name(item: dict[str, Any]) -> str:
    name = f"{item.get('brand', '')} {item.get('title', '')}".strip()
    return name if len(name) <= 20 else name[:20]


def _humanize_ids(text: Any, by_id: dict[str, dict[str, Any]]) -> str:
    value = str(text or "")
    for pid, item in by_id.items():
        token = str(pid)
        # 只替换真实商品编号（带下划线或足够长），避免把“a / t”这类单字符
        # 或普通中文里出现的短词一并抹掉。
        if token and (len(token) >= 4 or "_" in token):
            value = value.replace(token, _short_name(item))
    value = re.sub(r"p_[a-z0-9_]+", "该商品", value)
    return value


def _family_key(product: Any) -> str:
    """粗粒度去重：同一个品牌、同一个型号/标题前缀不应拿来做“横向”对比。"""
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", _clean(getattr(product, "title", "")).lower())
    tokens = [token for token in title.split() if token not in {"新版", "官方", "正品", "套装", "单品"}]
    # 型号通常在标题前部；保留前三个 token 足够排掉同款不同 SKU，
    # 又不会把整个子类错误视为一个产品族。
    return f"{_clean(getattr(product, 'brand', '')).lower()}:{' '.join(tokens[:3])}"


def _dossier_text(dossier: dict[str, Any]) -> str:
    pieces = [
        dossier.get("title", ""), dossier.get("brand", ""), dossier.get("sub_category", ""),
        dossier.get("marketing_description", ""),
    ]
    for faq in dossier.get("official_faq") or []:
        if isinstance(faq, dict):
            pieces.extend((faq.get("question", ""), faq.get("answer", "")))
    for sku in dossier.get("skus") or []:
        if isinstance(sku, dict):
            pieces.extend(str(v) for v in (sku.get("properties") or {}).values())
    return " ".join(str(piece) for piece in pieces if piece)


_FEATURE_LABELS = {
    "续航": (("续航", "长续航"),),
    "兼容性": (("兼容", "兼容信息已标注"),),
    "适用场景": (("通勤", "通勤"), ("运动", "运动"), ("户外", "户外")),
    "成分功效": (("保湿", "保湿"), ("修护", "修护"), ("防晒", "防晒")),
    "适用肤质": (("敏感", "敏感肌"), ("油", "油性肤质"), ("干", "干性肤质")),
    "性价比": (("大容量", "大容量"), ("套装", "套装")),
    "材质": (("纯棉", "纯棉"), ("涤纶", "涤纶"), ("皮", "皮质")),
    "尺码适配": (("偏大", "偏大"), ("偏小", "偏小"), ("标准", "标准尺码")),
    "穿搭场景": (("通勤", "通勤"), ("运动", "运动"), ("休闲", "休闲")),
    "口味": (("甜", "偏甜"), ("咸", "偏咸"), ("辣", "带辣味")),
    "健康程度": (("0糖", "0糖"), ("低糖", "低糖"), ("低脂", "低脂")),
    "规格划算度": (("家庭装", "家庭装"), ("大包装", "大包装"), ("大容量", "大容量")),
    "材质安全": (("食品级", "食品级"), ("无甲醛", "无甲醛")),
    "实用性": (("多功能", "多功能"), ("收纳", "收纳")),
    "空间适配": (("小户型", "小户型"), ("节省空间", "节省空间")),
    "安全性": (("安全", "安全信息已标注"),),
    "适用月龄": (("月龄", "适用月龄已标注"),),
    "材质成分": (("无", "成分信息已标注"),),
    "专业性能": (("专业", "专业性能描述"),),
    "耐用度": (("耐用", "耐用性描述"),),
    "适用运动": (("跑步", "跑步"), ("徒步", "徒步"), ("登山", "登山")),
    "成分温和度": (("温和", "温和"),),
    "清洁力": (("清洁", "清洁需求"),),
    "适用人群": (("敏感", "敏感肌"), ("儿童", "儿童")),
}


def _attributes(dossier: dict[str, Any], dimensions: list[str]) -> dict[str, str]:
    price_range = dossier.get("price_range") or {}
    low = price_range.get("min", dossier.get("price", 0))
    high = price_range.get("max", dossier.get("price", 0))
    text = _dossier_text(dossier).lower()
    attrs: dict[str, str] = {}
    for dimension in dimensions:
        if dimension == "价格":
            attrs[dimension] = f"¥{low}-¥{high}" if low != high else f"¥{low}"
            continue
        value = next((label for keyword, label in _FEATURE_LABELS.get(dimension, ()) if keyword in text), "")
        attrs[dimension] = value or "资料有限"
    return attrs


def _coverage(dossier: dict[str, Any]) -> int:
    review = dossier.get("review_summary") or {}
    return sum((
        bool(dossier.get("marketing_description")),
        bool(dossier.get("skus")),
        bool(dossier.get("official_faq")),
        bool(review.get("count")),
    ))


def _price_band(price: float, target_price: float) -> str:
    if price < target_price * 0.82:
        return "低价款"
    if price <= target_price * 1.22:
        return "同价位"
    return "升级款"


def _product_text(product: Any) -> str:
    parts = [getattr(product, "title", ""), getattr(product, "brand", ""), getattr(product, "sub_category", "")]
    knowledge = getattr(product, "rag_knowledge", None)
    if knowledge:
        parts.append(getattr(knowledge, "marketing_description", "") or "")
    return _clean(" ".join(parts)).lower()


def _query_concerns(query: str) -> set[str]:
    text = _clean(query).lower()
    return {
        keyword
        for keywords in _FEATURE_LABELS.values()
        for keyword, _label in keywords
        if keyword in text
    }


def _concern_hits(product: Any, concerns: set[str]) -> int:
    if not concerns:
        return 0
    text = _product_text(product)
    return sum(1 for keyword in concerns if keyword in text)


def select_comparable_products(repo: Any, target: Any, *, query: str = "", limit: int = 3) -> list[Any]:
    """按可比性和差异性选对手，而不是把“评价最高”的几款塞进来。

    先严格锁定同一子类（没有子类才退到品类），然后按低价/相近/升级价格带挑
    代表项；每个价格带内选择资料更完整的一件。剩余位置再由与目标价格距离、
    资料覆盖度确定。这让表格至少存在可解释的取舍，而非重复同款。
    """
    pool = repo.filter_by(category=target.category, sub_category=target.sub_category or None)
    target_key = _family_key(target)
    budget_max = None
    try:
        from app.decision.rules import detect_budget

        budget_max = detect_budget(query or "")
    except Exception:
        budget_max = None
    concerns = _query_concerns(query or "")
    unique: dict[str, Any] = {}
    for item in pool:
        if item.product_id == target.product_id or _family_key(item) == target_key:
            continue
        # 对比入口只比较可售、价格有效的同类商品。
        price = float(getattr(item, "base_price", 0) or 0)
        if price <= 0 or (budget_max is not None and price > budget_max):
            continue
        key = _family_key(item)
        prior = unique.get(key)
        if prior is None or _raw_coverage(item) > _raw_coverage(prior):
            unique[key] = item
    candidates = list(unique.values())
    if not candidates:
        return []

    target_price = max(float(getattr(target, "base_price", 0) or 0), 1.0)

    def sort_key(item: Any) -> tuple[float, float, float, str]:
        price = float(getattr(item, "base_price", 0) or 0)
        # 距离在同价格带内只用于保持可比，不是“好坏”评分。
        return (
            -_concern_hits(item, concerns),
            -_raw_coverage(item),
            abs(price - target_price) / target_price,
            str(item.product_id),
        )

    bands: list[Iterable[Any]] = (
        (item for item in candidates if float(item.base_price) < target_price * 0.82),
        (item for item in candidates if target_price * 0.82 <= float(item.base_price) <= target_price * 1.22),
        (item for item in candidates if float(item.base_price) > target_price * 1.22),
    )
    chosen: list[Any] = []
    for band in bands:
        options = sorted(list(band), key=sort_key)
        if options:
            chosen.append(options[0])
    for item in sorted(candidates, key=sort_key):
        if item not in chosen:
            chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen[:limit]


def _raw_coverage(product: Any) -> int:
    knowledge = getattr(product, "rag_knowledge", None)
    if not knowledge:
        return 0
    return sum((
        bool(getattr(knowledge, "marketing_description", "")),
        bool(getattr(knowledge, "official_faq", None)),
        bool(getattr(knowledge, "user_reviews", None)),
        bool(getattr(product, "skus", None)),
    ))


def _item(dossier: dict[str, Any], dimensions: list[str], *, role: str) -> dict[str, Any]:
    review = dossier.get("review_summary") or {}
    price_range = dossier.get("price_range") or {}
    price = dossier.get("price", 0)
    evidence = []
    if dossier.get("skus"):
        evidence.append("规格已核对")
    if dossier.get("official_faq"):
        evidence.append(f"官方问答 {len(dossier['official_faq'])} 条")
    if review.get("count"):
        evidence.append(f"用户评价 {review.get('count')} 条")
    return {
        "product_id": dossier.get("product_id"), "title": dossier.get("title"), "brand": dossier.get("brand"),
        "price": price,
        "price_range": {"min": price_range.get("min", price), "max": price_range.get("max", price)},
        "image_url": f"/api/products/{dossier.get('product_id')}/image",
        "rating": {"avg": review.get("avg_rating"), "count": review.get("count", 0)},
        "attributes": _attributes(dossier, dimensions),
        "highlights": evidence[:2], "cautions": list(dossier.get("information_gaps") or [])[:2],
        "suitable_for": "待欧米结合你的需求判断", "comparison_role": role,
        "evidence_status": dossier.get("evidence_status", "信息有限"),
    }


def _safe_json(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if "```" in raw:
        raw = raw.split("```")[1].removeprefix("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _fallback_verdict(items: list[dict[str, Any]]) -> dict[str, Any]:
    if len(items) < 2:
        return {"text": "当前资料里没有足够的同类商品可做可靠横向比较。", "winner_id": None,
                "reasons": ["同类候选不足"]}
    if len(items) < 3:
        return {"text": "当前同类可选款较少，欧米仅对比了少量可核对的商品。", "winner_id": None,
                "reasons": ["同类候选不足"]}
    prices = [float(item.get("price", 0) or 0) for item in items]
    return {
        "text": "我按同一子类、价格带和已核对资料挑出这些可比款；没有脱离使用场景的绝对胜者。",
        "winner_id": None,
        "reasons": [f"价格范围 ¥{min(prices):g}–¥{max(prices):g}", "规格与资料完整度已核对"],
    }


def _apply_judgement(comparison: dict[str, Any], raw: dict[str, Any]) -> bool:
    items = [comparison["target"], *comparison["alternatives"]]
    allowed = {str(item.get("product_id")) for item in items}
    by_id = {str(item.get("product_id")): item for item in items}
    judgement_items = raw.get("items")
    if not isinstance(judgement_items, list):
        return False
    winner_id = raw.get("winner_id")
    if winner_id is not None and str(winner_id) not in allowed:
        return False
    changes = {str(row.get("product_id")): row for row in judgement_items if isinstance(row, dict)}
    if not changes or not set(changes).issubset(allowed):
        return False
    text = _humanize_ids(raw.get("verdict_text"), by_id)[:80]
    if len(text) < 8:
        return False
    for item in items:
        row = changes.get(str(item.get("product_id")), {})
        reason = _humanize_ids(row.get("choice_reason"), by_id)[:48]
        caution = _humanize_ids(row.get("caution"), by_id)[:36]
        if reason:
            item["suitable_for"] = reason
        if caution and caution not in item["cautions"]:
            item["cautions"] = [*item["cautions"], caution][:2]
    comparison["verdict"] = {
        "text": text,
        "winner_id": str(winner_id) if winner_id is not None else None,
        "reasons": [_humanize_ids(reason, by_id)[:24] for reason in raw.get("reasons", []) if _clean(reason)][:3],
    }
    comparison["judge_status"] = "model"
    return True


def _judge_input(comparison: dict[str, Any], query: str) -> str:
    items = [comparison["target"], *comparison["alternatives"]]
    rows = []
    for item in items:
        rows.append({
            "product_id": item["product_id"], "name": f"{item.get('brand', '')} {item.get('title', '')}",
            "price": item.get("price"), "attributes": item.get("attributes"),
            "evidence": item.get("highlights"), "information_gaps": item.get("cautions"),
        })
    return (
        f"用户的对比请求：{_clean(query)}\n"
        "目标商品是列表中的第一个；其余为经过同子类、不同价格带与同款去重筛出的候选。\n"
        "可用商品事实：\n" + json.dumps(rows, ensure_ascii=False)
    )


async def build_same_category_comparison(repo: Any, target: Any, query: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """构造可展示比较表并要求 LLM 在闭集事实中给出选购裁决。"""
    target_dossier = build_product_dossier(target, "overview")
    candidates = select_comparable_products(repo, target, query=query)
    dossiers = {target.product_id: target_dossier}
    for product in candidates:
        dossiers[product.product_id] = build_product_dossier(product, "overview")
    dimensions = CATEGORY_DIMENSIONS.get(target.category, CATEGORY_DIMENSIONS_DEFAULT)
    target_price = max(float(getattr(target, "base_price", 0) or 0), 1.0)
    target_item = _item(target_dossier, dimensions, role="当前查看")
    target_item["price_band"] = None
    alternatives = []
    for product in candidates:
        item = _item(dossiers[product.product_id], dimensions, role="同类备选")
        item["price_band"] = _price_band(float(getattr(product, "base_price", 0) or 0), target_price)
        alternatives.append(item)
    comparison = {
        "dimensions": dimensions, "target": target_item, "alternatives": alternatives,
        "verdict": _fallback_verdict([target_item, *alternatives]),
        "selection_method": "同子类范围、同款去重、低价/相近/升级价格带、资料可核对性",
        "judge_status": "fallback",
    }
    if alternatives:
        try:
            raw_text = await asyncio.wait_for(
                get_model_gateway().chat("chat_generation", _judge_input(comparison, query), _COMPARISON_JUDGE_SYSTEM),
                timeout=12.0,
            )
            _apply_judgement(comparison, _safe_json(raw_text))
        except Exception:
            # 资料表和最终回答都能继续工作；只有这一次模型裁决失败才走受控结论。
            pass
    return comparison, dossiers
