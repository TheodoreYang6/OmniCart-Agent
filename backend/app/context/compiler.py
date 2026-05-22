"""V1 Context Compiler — 将 WorkflowState 编译为 LLM-ready 结构化上下文。

不把原始检索结果直接丢给 LLM，而是先编译成干净的结构化上下文。
"""

from app.schemas.workflow import WorkflowState


def compile_context(state: WorkflowState) -> str:
    """编译完整购物决策上下文给 Response Agent"""
    parts = []

    # 1. 用户意图
    parts.append("## 用户需求")
    parts.append(f"查询: {state.user_query}")
    if state.intent:
        parts.append(f"意图: {state.intent}")

    # 2. 约束条件
    c = state.constraints
    constraints_text = []
    if c.category:
        constraints_text.append(f"品类={c.category}")
    if c.sub_category:
        constraints_text.append(f"子类={c.sub_category}")
    if c.budget_max:
        constraints_text.append(f"预算上限={c.budget_max}元")
    if c.budget_min:
        constraints_text.append(f"预算下限={c.budget_min}元")
    if c.scenario:
        constraints_text.append(f"场景={c.scenario}")
    if c.must_tags:
        constraints_text.append(f"必须包含={c.must_tags}")
    if c.exclude_tags:
        constraints_text.append(f"排除={c.exclude_tags}")
    if constraints_text:
        parts.append(f"约束: {', '.join(constraints_text)}")

    # 3. 视觉解析结果
    if state.visual_result:
        vr = state.visual_result
        parts.append("\n## 图片识别结果")
        if vr.get("product_name"):
            parts.append(f"商品名: {vr['product_name']}")
        if vr.get("brand"):
            parts.append(f"品牌: {vr['brand']}")
        if vr.get("price"):
            parts.append(f"价格: ¥{vr['price']}")
        if vr.get("capacity"):
            parts.append(f"容量: {vr['capacity']}")
        if vr.get("power"):
            parts.append(f"功率: {vr['power']}")
        parts.append(f"识别置信度: {vr.get('confidence', 0)}")

    # 4. 候选商品
    products = state.retrieved_products[:5]
    if products:
        parts.append("\n## 候选商品")
        for i, p in enumerate(products, 1):
            pid = p.get("product_id", "")
            title = p.get("title", "")
            price = p.get("price", 0)
            category = p.get("category", "")
            sub = p.get("sub_category", "")

            # 匹配评分
            score_info = ""
            for d in state.decision_results:
                if d.get("product_id") == pid:
                    ds = d.get("display_score", 0)
                    reason = d.get("recommendation_reason", "")[:80]
                    risks = d.get("risk_factors", [])
                    score_info = f" | 推荐分={ds}/10"
                    if reason:
                        score_info += f" | {reason}"
                    if risks:
                        score_info += f" | 风险: {', '.join(risks[:2])}"
                    break

            parts.append(f"{i}. [{category}/{sub}] {title[:60]} — ¥{price}{score_info}")

    # 5. 证据摘要
    if state.evidence_list:
        evidence = state.evidence_list
        types = {}
        for e in evidence:
            t = e.get("source_type", "other")
            types[t] = types.get(t, 0) + 1
        parts.append(f"\n## 证据 ({len(evidence)}条)")
        parts.append(", ".join(f"{v}条{t}" for t, v in types.items()))

        # 摘录几条关键证据
        key_evidence = [e for e in evidence if e.get("source_type") in ("review_risk", "policy_faq")][:3]
        for e in key_evidence:
            parts.append(f"- [{e.get('source_type','')}] {e.get('content','')[:120]}")

    # 6. 反事实建议（0结果时）
    if not products and state.constraints.budget_max:
        parts.append("\n## 反事实建议")
        parts.append(f"当前预算 ¥{state.constraints.budget_max} 无匹配商品。")
        parts.append(f"请建议用户放宽预算到 ¥{state.constraints.budget_max * 1.5:.0f} 左右，")
        parts.append(f"或更换品类/关键词重新搜索。")

    # 7. 检索计划
    plan = state.retrieval_plan
    if plan.channels:
        parts.append(f"\n检索渠道: {', '.join(plan.channels)}, top_k={plan.top_k}")

    return "\n".join(parts)
