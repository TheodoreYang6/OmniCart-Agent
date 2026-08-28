"""可复算的用户展示评分。

这个分数不是向量相似度，也不是商品的绝对质量分。它只回答一件事：
在*本次用户问题*和已验证资料下，这件商品有多值得优先看。模型只能在
闭集候选中给出 ``filter_bucket``；所有数值、等级和资料状态均由本模块
按确定性规则计算，避免 rerank 分、旧校准分和 UI 标签彼此矛盾。
"""

from __future__ import annotations

from typing import Any


_VERDICT_BASE = {
    "primary": 94,
    "alternative": 76,
    "conditional": 58,
    "exclude": 25,
}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_texts(values: Any) -> list[str]:
    return [str(value).strip().lower() for value in (values or []) if str(value).strip()]


def _source_types(product: dict[str, Any]) -> set[str]:
    """统计可追溯的资料来源，而非统计重复 Chunk 数。"""
    kinds: set[str] = set()
    for fact in product.get("product_facts") or []:
        if bool(fact.get("verified", False)):
            kinds.add("商品参数")
            break
    for chunk in product.get("matched_chunks") or []:
        payload = chunk.get("payload", chunk) if isinstance(chunk, dict) else {}
        kind = str(payload.get("chunk_type") or payload.get("source_type") or "").lower()
        if kind in {"identity", "facts"}:
            kinds.add("商品参数")
        elif kind in {"marketing", "description"}:
            kinds.add("商品说明")
        elif kind == "faq":
            kinds.add("官方问答")
        elif kind in {"review", "review_aspect"}:
            kinds.add("用户评价")
    for kind in product.get("evidence_types") or []:
        normalized = str(kind).lower()
        if normalized in {"identity", "facts"}:
            kinds.add("商品参数")
        elif normalized in {"marketing", "description"}:
            kinds.add("商品说明")
        elif normalized == "faq":
            kinds.add("官方问答")
        elif normalized in {"review", "review_aspect"}:
            kinds.add("用户评价")
    knowledge = product.get("rag_knowledge") or {}
    if knowledge.get("official_faq"):
        kinds.add("官方问答")
    if knowledge.get("user_reviews"):
        kinds.add("用户评价")
    if knowledge.get("marketing_description") or product.get("description"):
        kinds.add("商品说明")
    return kinds


def _budget_score(price: float | None, budget_max: float | None) -> tuple[int | None, str]:
    if budget_max is None or budget_max <= 0:
        return None, "未设置预算，不纳入本次指数"
    if price is None or price <= 0:
        return None, "价格信息缺失，未纳入本次指数"
    ratio = price / budget_max
    if ratio > 1:
        return 0, "超出本次预算"
    if ratio <= 0.40:
        return 100, "明显低于预算上限"
    if ratio <= 0.65:
        return 94, "预算余量充足"
    if ratio <= 0.85:
        return 88, "处于舒适预算区间"
    return 80, "接近预算上限"


def _information_score(sources: set[str]) -> tuple[int, str]:
    count = len(sources)
    if count >= 4:
        return 100, "资料充分"
    if count == 3:
        return 86, "资料较完整"
    if count == 2:
        return 72, "资料基本够用"
    if count == 1:
        return 55, "资料有限"
    return 35, "资料有限"


def _need_score(bucket: str, hard_failed: bool) -> tuple[int, str]:
    if hard_failed:
        return 20, "未满足本次硬条件"
    score = _VERDICT_BASE.get(bucket, 58)
    text = {
        "primary": "已通过本次需求筛选",
        "alternative": "符合主要需求，可作备选",
        "conditional": "部分条件仍需确认",
        "exclude": "不适合优先考虑",
    }.get(bucket, "与当前需求有一定关联")
    return score, text


def _avoid_hit(product: dict[str, Any], constraints: Any) -> bool:
    avoid = _as_texts(getattr(constraints, "exclude_tags", []) if constraints else [])
    if not avoid:
        return False
    text = " ".join(str(product.get(key) or "") for key in ("title", "brand", "category", "sub_category")).lower()
    return any(term in text for term in avoid)


def _weighted_average(dimensions: list[tuple[int, int | None, int]]) -> int:
    """(权重, 分数, 可用标记)；不可用维度自动重新分配权重。"""
    active = [(weight, score) for weight, score, enabled in dimensions if enabled and score is not None]
    if not active:
        return 0
    weight_total = sum(weight for weight, _ in active)
    return round(sum(weight * score for weight, score in active) / weight_total)


def build_recommendation_score(product: dict[str, Any], constraints: Any | None = None) -> dict[str, Any]:
    """返回单一、稳定且可以从请求快照重算的评分卡。"""
    bucket = str(product.get("filter_bucket") or "conditional")
    price = _number(product.get("price"))
    budget = _number(getattr(constraints, "budget_max", None) if constraints else None)
    hard_failed = str(product.get("hard_constraint_status") or "") == "failed"
    if budget is not None and price is not None and price > budget:
        hard_failed = True
    if _avoid_hit(product, constraints):
        hard_failed = True

    need, need_detail = _need_score(bucket, hard_failed)
    budget_fit, budget_detail = _budget_score(price, budget)
    sources = _source_types(product)
    information, information_label = _information_score(sources)
    total = _weighted_average([
        (60, need, 1),
        (20, budget_fit, int(budget_fit is not None)),
        (20, information, 1),
    ])
    # 硬约束不可被资料多或低价“冲高”；条件候选也不应伪装成强推荐。
    if hard_failed or bucket == "exclude":
        total = min(total, 39)
        level = "not_recommended"
        match_label = "暂不建议优先"
    elif bucket == "conditional":
        total = min(total, 69)
        level = "worth_considering"
        match_label = "有条件匹配"
    elif bucket == "primary":
        total = max(82, min(total, 98))
        level = "strong_recommend"
        match_label = "高度匹配"
    else:
        total = max(65, min(total, 84))
        level = "recommended"
        match_label = "较匹配"

    evidence_label = "证据充分" if information >= 72 else "信息有限"
    return {
        "version": "omi_recommendation_v1",
        "label": "欧米适配指数",
        "score": total,
        "match_label": match_label,
        "recommendation_level": level,
        "evidence_label": evidence_label,
        "information_status": information_label,
        "source_types": sorted(sources),
        "dimensions": [
            {"key": "need_fit", "label": "需求契合", "score": need, "detail": need_detail},
            {"key": "budget_fit", "label": "预算适配", "score": budget_fit, "detail": budget_detail},
            {"key": "information", "label": "资料完整", "score": information, "detail": information_label},
        ],
        "explanation": "依据本次需求筛选、预算与可追溯商品资料计算，仅用于本次对比，不代表商品绝对质量。",
    }
