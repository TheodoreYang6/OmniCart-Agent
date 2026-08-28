"""V3 Context Compiler — 压缩版，只传 Top 3 + 关键证据，控制 prompt 体积。"""

import logging

from app.framework.context import create_token_estimator
from app.schemas.workflow import WorkflowState

_log = logging.getLogger("omnicart.prompt")

# Response prompt token 预算安全网：正常 Top-N 提示远低于此值，仅在极端长上下文时截断。
_PROMPT_TOKEN_BUDGET = 3000
_estimator = create_token_estimator()


def compile_context(state: WorkflowState, context_bundle=None) -> str:
    """编译压缩版购物决策上下文给 Response Agent。

    V3 压缩策略:
    - Top 3 商品，每商品 ≤3 条 evidence summary，每条 ≤120 字
    - 不传完整 product json / reviews / faq
    """
    parts = []

    # 0. 上下文块：优先消费 ContextManager 组装的 ContextBundle（多源采集 + token 预算裁剪）；
    #    未提供时回退到 FollowUpEngine 的 context_prompt（向后兼容）。
    ctx_text = ""
    if context_bundle is not None and getattr(context_bundle, "text", ""):
        ctx_text = context_bundle.text
    elif state.context_prompt:
        ctx_text = state.context_prompt
    if ctx_text:
        parts.append(ctx_text)
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

    # 4. 候选商品。若 SSE 已锁定推荐简报，模型只能看到首选 1-3 款，
    # 防止“正文提到备选、首选卡却是另一批商品”。未锁定时保留旧 Top 5 行为。
    primary_ids = list(getattr(state, "primary_product_ids", None) or [])
    if primary_ids:
        by_id = {p.get("product_id"): p for p in state.retrieved_products}
        products = [by_id[pid] for pid in primary_ids if pid in by_id]
    else:
        products = state.retrieved_products[:5]
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
            facts = p.get("product_facts", []) or []
            if facts:
                visible = []
                for fact in facts[:8]:
                    key = fact.get("fact_key", "")
                    label = {
                        "nutrition.zero_sugar": "0糖", "nutrition.low_sugar": "低糖",
                        "nutrition.zero_fat": "0脂", "nutrition.low_fat": "低脂",
                        "nutrition.zero_calorie": "0卡", "nutrition.low_calorie": "低卡",
                        "nutrition.high_protein": "高蛋白",
                    }.get(key)
                    if label:
                        visible.append(label)
                if visible:
                    parts.append(f"   可验证属性: {'、'.join(dict.fromkeys(visible))}")

        # 引用集写回 state；锁定首选时这恰好是首选 ID，不得再被扩展为长候选列表。
        try:
            state.answer_cited_pids = [p for p in candidate_pids if p]
        except Exception:  # noqa: BLE001 — 写回失败不影响回答生成
            pass

        # 关键证据：每张首选卡至少有一条，避免第三张卡在文案中变成
        # “只有标题没有理由”的黑盒推荐。
        if state.evidence_list:
            evidence_lines = []
            for pid in candidate_pids:
                product_evs = [e for e in state.evidence_list if e.get("product_id") == pid]
                if product_evs:
                    for e in product_evs[:1]:
                        content = e.get("content", "")[:80]
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

    # Token 预算安全网：超预算时按比例截断（保留头部：需求/约束/候选，尾部证据先舍）
    result = _enforce_token_budget(result)

    # 最终回答已由 ConversationContextAssembler 负责结构化审计；旧编译器不能再
    # 将完整 prompt 追加写入无限增长的 audit_prompts.log（其中会包含会话内容）。

    return result


def _enforce_token_budget(text: str) -> str:
    """估算 prompt token，超预算则按比例截断（安全网，正常不触发）。"""
    try:
        tokens = _estimator.estimate(text)
        if tokens <= _PROMPT_TOKEN_BUDGET:
            return text
        ratio = _PROMPT_TOKEN_BUDGET / max(tokens, 1)
        keep = max(1, int(len(text) * ratio) - 20)
        _log.warning(
            "compiled prompt over budget: %d tokens > %d, truncating", tokens, _PROMPT_TOKEN_BUDGET
        )
        return text[:keep] + "\n…[上下文超预算已截断]"
    except Exception:
        return text


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
            decision = ""
            for d in state.decision_results:
                if d.get("product_id") == pid:
                    decision = d.get("match_label") or d.get("recommendation_level", "")
                    break
            products.append({
                "id": pid,
                "title": p.get("title", "")[:60],
                "brand": p.get("brand", ""),
                "price": p.get("price", 0),
                "reranker": round(p.get("reranker_score", 0), 3),
                "decision": decision,
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
