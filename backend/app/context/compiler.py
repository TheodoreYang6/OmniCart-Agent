"""V3 Context Compiler — 压缩版，只传 Top 3 + 关键证据，控制 prompt 体积。"""

import logging
from app.schemas.workflow import WorkflowState

_log = logging.getLogger("omnicart.prompt")


def compile_context(state: WorkflowState) -> str:
    """编译压缩版购物决策上下文给 Response Agent。

    V3 压缩策略:
    - Top 3 商品，每商品 ≤3 条 evidence summary，每条 ≤120 字
    - 不传完整 product json / reviews / faq
    """
    parts = []

    # 0. FollowUpEngine 上下文提示（仅 Response Agent 使用）
    if state.context_prompt:
        parts.append(state.context_prompt)
        parts.append("")

    # 1. 用户意图
    parts.append("## 用户需求")
    parts.append(f"查询: {state.user_query}")
    if state.intent:
        parts.append(f"意图: {state.intent}")

    # 2. 约束条件
    c = state.constraints
    constraints_parts = []
    if c.category:
        constraints_parts.append(f"品类={c.category}")
    if c.sub_category:
        constraints_parts.append(f"子类={c.sub_category}")
    if c.budget_max:
        constraints_parts.append(f"预算上限={c.budget_max}元")
    if c.budget_min:
        constraints_parts.append(f"预算下限={c.budget_min}元")
    if c.scenario:
        constraints_parts.append(f"场景={c.scenario}")
    if constraints_parts:
        parts.append(f"约束: {', '.join(constraints_parts)}")

    # 3. 视觉结果 — 优先告知用户
    if state.visual_result:
        vr = state.visual_result
        vis_parts = []
        if vr.get("product_name"):
            vis_parts.append(f"商品={vr['product_name']}")
        if vr.get("brand"):
            vis_parts.append(f"品牌={vr['brand']}")
        if vr.get("price"):
            vis_parts.append(f"价格={vr['price']}")
        if vis_parts:
            parts.append("")
            parts.append(f"⚠️ 用户上传了商品图片，识别结果: {', '.join(vis_parts)}。")
            parts.append("拍照识图=搜同款意图。请先介绍同款商品（如有），再横向推荐同类商品。分清'这就是这款👇'和'同类推荐📌'。")

    # 4. 候选商品 — 有视觉结果时传 Top 5（防止识图目标被挤出前3）
    top_n = 5 if state.visual_result else 3
    products = state.retrieved_products[:top_n]
    candidate_pids = []
    if products:
        parts.append("\n## 候选商品")
        for i, p in enumerate(products, 1):
            pid = p.get("product_id", "")
            candidate_pids.append(pid)
            title = p.get("title", "")
            price = p.get("price", 0)
            category = p.get("category", "")
            brand = p.get("brand", "")
            reranker_score = p.get("reranker_score", 0)

            # 匹配度描述
            match_desc = ""
            if reranker_score and reranker_score > 0.75:
                match_desc = "，与你描述的需求很契合"
            elif reranker_score and reranker_score > 0.5:
                match_desc = "，基本匹配你的需求"

            parts.append(f"{i}. {brand} {title[:50]} — ¥{price}{match_desc}")

        # 关键证据 (每商品1条，≤100字)
        if state.evidence_list:
            evidence_lines = []
            for pid in candidate_pids[:2]:
                product_evs = [e for e in state.evidence_list if e.get("product_id") == pid]
                if product_evs:
                    for e in product_evs[:1]:
                        content = e.get("content", "")[:100]
                        if content and "余弦相似度" not in content:
                            evidence_lines.append(f"  [{pid}] {content}")
            if evidence_lines:
                parts.append("关键证据:")
                parts.extend(evidence_lines)

    # 5. 反事实建议 (0结果时)
    if not products:
        parts.append("\n## 无匹配商品")
        msg = "请诚实告知用户未找到匹配商品。"
        if state.constraints.budget_max:
            msg += f" 建议放宽预算到 {state.constraints.budget_max * 1.5:.0f} 元或更换关键词。"
        parts.append(msg)

    # 6. 记忆提示 (如有)
    if state.used_memories:
        mem_hints = []
        for m in state.used_memories[:2]:
            mem_hints.append(m.get("content", "")[:60])
        if mem_hints:
            parts.append(f"\n用户偏好: {'; '.join(mem_hints)}")

    result = "\n".join(parts)

    # 写入日志文件供审计
    _write_audit_log(state, result)

    return result


def _write_audit_log(state: WorkflowState, prompt: str):
    """每次查询将候选商品和完整 prompt 写入 data/audit_prompts.log。"""
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    try:
        log_file = Path(__file__).resolve().parent.parent.parent.parent / "data" / "audit_prompts.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        products = []
        for p in state.retrieved_products[:5]:
            pid = p.get("product_id", "")
            score = ""
            for d in state.decision_results:
                if d.get("product_id") == pid:
                    score = f"{d.get('display_score',0)}/10 {d.get('recommendation_level','')}"
                    break
            products.append({
                "id": pid,
                "title": p.get("title", "")[:60],
                "brand": p.get("brand", ""),
                "price": p.get("price", 0),
                "reranker": round(p.get("reranker_score", 0), 3),
                "score": score,
            })

        entry = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "query": state.user_query[:120],
            "intent": state.intent,
            "category": state.constraints.category,
            "candidates": products,
            "prompt": prompt,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n---\n")
    except Exception:
        pass
