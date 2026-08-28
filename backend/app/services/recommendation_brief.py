"""将决策结果收敛为面向用户的推荐简报。

简报是答文、首选卡和备选卡的唯一商品口径：模型只能引用首选商品，
客户端也不再依据一个长候选列表自行判断视觉优先级。
"""

from __future__ import annotations

import re

from app.schemas.workflow import WorkflowState

PRIMARY_LIMIT = 3
ALTERNATIVE_LIMIT = 6


def _family_key(product: dict) -> str:
    """保守识别同一型号族，避免首选卡被同款不同规格占满。

    数据集没有稳定的 model_family 字段时，不能仅按品牌去重（会把不同型号
    错删）。这里保留品牌，并取去品牌后的连续产品名前缀；只有同品牌且前缀
    足够长才认为同族。像 Redmi Buds 5 Pro 的 10mm/12mm 变体会合并，
    iPhone 15 与 iPhone 15 Pro、不同品类则不会误合并。
    """
    brand = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(product.get("brand") or "").lower())
    title = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(product.get("title") or "").lower())
    if brand and title.startswith(brand):
        title = title[len(brand):]
    return f"{brand}:{title}"


def _same_family(left: dict, right: dict) -> bool:
    left_key, right_key = _family_key(left), _family_key(right)
    left_brand, left_title = left_key.split(":", 1)
    right_brand, right_title = right_key.split(":", 1)
    if not left_brand or left_brand != right_brand or not left_title or not right_title:
        return False
    prefix = 0
    for a, b in zip(left_title, right_title):
        if a != b:
            break
        prefix += 1
    # 12 个归一化字符足以包含系列/型号，仍远短于常见营销尾巴。
    return prefix >= 12


def _match_label(decision: dict) -> str:
    if decision.get("hard_constraint_status") == "failed" or \
            decision.get("recommendation_level") == "not_recommended":
        return "不建议优先"
    return {
        "strong_recommend": "高度匹配",
        "recommended": "较匹配",
        "worth_considering": "有条件匹配",
        "cautious": "有条件匹配",
        "insufficient_evidence": "信息有限",
    }.get(decision.get("recommendation_level", ""), "有条件匹配")


def _evidence_label(decision: dict, sufficient: bool) -> str:
    confidence = float(decision.get("evidence_confidence") or 0)
    return "证据充分" if sufficient and confidence >= 0.55 else "信息有限"


def build_recommendation_brief(state: WorkflowState) -> tuple[list[dict], list[dict]]:
    """锁定最多三款首选与六款备选，并将展示语义写回决策结果。"""
    product_by_id = {
        p.get("product_id"): p for p in (state.retrieved_products or [])
        if p.get("product_id")
    }
    decision_by_id = {
        d.get("product_id"): d for d in (state.decision_results or [])
        if d.get("product_id")
    }
    # ``exact_product`` 不经过泛检索，因此没有 v9 retrieval report；但它和
    # v9 的闭集交付一样，必须复用同一份展示裁决，不能悄悄退回旧分数语义。
    v9_active = (
        (getattr(state, "structured_retrieval_report", {}) or {}).get("version") == "v9"
        or (getattr(state, "retrieval_scope", "") == "exact_product")
    )

    # ReAct 显式选品优先；否则沿用 DecisionAgent 已按真实 final_score 排好的顺序。
    selected_ids = [p.get("product_id") for p in (state.selected_products or [])
                    if p.get("product_id") in product_by_id]
    ranked_ids = ([p.get("product_id") for p in (state.retrieved_products or []) if p.get("product_id")]
                  if v9_active else
                  [d.get("product_id") for d in (state.decision_results or [])
                   if d.get("product_id") in product_by_id])
    ordered_ids: list[str] = []
    for pid in selected_ids + ranked_ids + list(product_by_id):
        if pid and pid not in ordered_ids:
            ordered_ids.append(pid)

    # 精确型号只给一个首选；同型号变体作为最多两项备选。
    # 已锁定系列的候选本身不超过三项，不再从泛检索扩充备选。
    scope = getattr(state, "retrieval_scope", "broad") or "broad"
    primary_limit = 1 if scope == "exact_product" else PRIMARY_LIMIT
    # 多目标的首选区是“每个用户目标的一张答案卡”，不是全局候选排行榜。
    # 当饮品缺失时继续塞两张零食主推，会让用户误以为系统忽略了饮品诉求。
    group_delivery = len(getattr(state, "retrieval_groups", []) or []) > 1
    # Compound requests must not silently collapse to the globally highest
    # scoring group.  Reserve one first-choice slot for every matched group
    # (up to the normal three-card user-facing limit), then fill by rank.
    primary_ids: list[str] = []

    def add_primary(pid: str, *, allow_same_family: bool = False) -> bool:
        """加入首选，同时避免同型号变体挤占有限的三张卡。"""
        if not pid or pid in primary_ids:
            return False
        product = product_by_id[pid]
        if not allow_same_family and any(_same_family(product, product_by_id[old]) for old in primary_ids):
            return False
        primary_ids.append(pid)
        return True

    if v9_active:
        # 单品聚焦的卡片是用户刚刚点选的主体，即使它对某个具体场景属于
        # conditional，也必须保留为首卡，让用户看到明确的注意点而非“消失”。
        if scope == "exact_product":
            for pid in ordered_ids[:1]:
                add_primary(pid, allow_same_family=True)
        # Filter 已确认的 primary/alternative 是唯一排序真源；Decision 只补充
        # 展示信息，不能再次按旧评分把被排除商品挤回首选。多目标请求还必须
        # 给每个已命中组保留一张首选，不能让后一次工具调用的同类候选吞掉前组。
        for group in getattr(state, "retrieval_groups", []) or []:
            status = group.get("status", "") if isinstance(group, dict) else getattr(group, "status", "")
            product_ids = group.get("product_ids", []) if isinstance(group, dict) else getattr(group, "product_ids", [])
            if status != "matched":
                continue
            pid = next((candidate for candidate in ordered_ids
                        if candidate in product_ids and product_by_id[candidate].get("filter_bucket") == "primary"), "")
            # 不同用户目标优先保证覆盖；即便标题恰好相近，也不能因此让某个
            # Router 组没有交付卡片。
            if pid:
                add_primary(pid, allow_same_family=True)
            if len(primary_ids) >= primary_limit:
                break
        if not group_delivery:
            for pid in ordered_ids:
                if len(primary_ids) >= primary_limit:
                    break
                if product_by_id[pid].get("filter_bucket") == "primary":
                    add_primary(pid)
    elif scope == "broad":
        for group in getattr(state, "retrieval_groups", []) or []:
            if isinstance(group, dict):
                group_status = group.get("status", "")
                gids = group.get("product_ids", [])
            else:
                group_status = getattr(group, "status", "")
                gids = getattr(group, "product_ids", [])
            if group_status != "matched":
                continue
            # Group retrieval order is only a recall order.  Pick the best item
            # for that group from the post-rerank/Decision ordering instead.
            first = next((pid for pid in ordered_ids if pid in gids), "")
            if first:
                add_primary(first, allow_same_family=True)
                if len(primary_ids) >= primary_limit:
                    break
    if not v9_active:
        for pid in ordered_ids:
            if len(primary_ids) >= primary_limit:
                break
            add_primary(pid)
    alternative_limit = 2 if scope == "exact_product" else ALTERNATIVE_LIMIT
    # Reserved group representatives need not occupy the first N global slots.
    # Slice-by-position drops valid candidates (and can even duplicate a primary)
    # in compound requests; derive alternatives by identity instead.
    if v9_active:
        # 多目标中未进入“每组一张”主推位的同组 primary，语义上是备选而不是又一张
        # 主推卡；保留它们，避免 Filter 的好候选被无声丢弃。
        alternative_source = [
            pid for pid in ordered_ids
            if pid not in primary_ids and product_by_id[pid].get("filter_bucket") in {"primary", "alternative", "conditional"}
        ]
        alternative_ids = alternative_source[:alternative_limit]
    else:
        alternative_ids = [pid for pid in ordered_ids if pid not in primary_ids][:alternative_limit]
    sufficient = bool((state.sufficiency_report or {}).get("sufficient", True))
    brief: list[dict] = []
    for pid in ordered_ids:
        decision = decision_by_id.get(pid, {})
        product = product_by_id[pid]
        if v9_active:
            bucket = product.get("filter_bucket", "")
            # DecisionAgent 已经依据本轮约束给出 v9 的最终标签。这里仅在
            # 兼容调用方漏字段时兜底，绝不重新计算并覆盖它。
            decision["match_label"] = decision.get("match_label") or (
                "高度匹配" if bucket == "primary" else
                "有条件匹配" if bucket == "conditional" else "较匹配"
            )
            decision["evidence_label"] = decision.get("evidence_label") or (
                "证据充分" if product.get("evidence_types") else "信息有限"
            )
            decision["why_it_fits"] = decision.get("why_it_fits") or product.get("card_reason") or "与当前需求更接近"
        else:
            decision["match_label"] = _match_label(decision)
            decision["evidence_label"] = _evidence_label(decision, sufficient)
            decision["why_it_fits"] = decision.get("recommendation_reason") or "与当前需求更接近"
        decision["caution"] = "；".join(str(x) for x in (decision.get("risk_factors") or [])[:2])
        if pid in primary_ids:
            brief.append({
                "product_id": pid,
                "title": product_by_id[pid].get("title", ""),
                "brand": product_by_id[pid].get("brand", ""),
                "price": product_by_id[pid].get("price", 0),
                "match_label": decision["match_label"],
                "evidence_label": decision["evidence_label"],
                "why_it_fits": decision["why_it_fits"],
                "caution": decision["caution"],
                "recommendation_score": decision.get("recommendation_score") or {},
            })

    state.primary_product_ids = primary_ids
    state.alternative_product_ids = alternative_ids
    state.answer_cited_pids = primary_ids
    state.recommendation_brief = brief
    # 简报由 ConversationContextAssembler 直接消费；不要再写回 context_prompt，
    # 否则 FollowUp/Loop 可能将它和旧工具文本重复送给最终模型。
    return ([product_by_id[pid] for pid in primary_ids],
            [product_by_id[pid] for pid in alternative_ids])
