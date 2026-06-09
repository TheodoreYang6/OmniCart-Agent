"""SSE 流式端点 — 正常推荐 / 商品聚焦分析 / 直接下单"""
import asyncio, json, logging, uuid as _uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.workflow.graph import run_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["stream"])


class StreamRequest(BaseModel):
    session_id: str = ""
    user_id: str = ""
    conversation_id: str = ""
    message: str = ""
    image_url: str | None = None
    mode: str = "normal_recommend"
    target_product_id: str | None = None
    allow_same_category_comparison: bool = False


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


_LEVEL_CN = {
    "strong_recommend": "强烈推荐", "recommended": "值得推荐",
    "cautious": "谨慎考虑", "insufficient_evidence": "证据不足",
    "not_recommended": "不推荐",
}


# ============================================================
# 辅助: 上下文增强
# ============================================================

def _extract_question(answer: str) -> str | None:
    """从豆仔回复中提取问句，供下一轮 Router 做问答链匹配。

    只匹配真正的问句 — 以？结尾，或以"吗/吧"结尾的疑问句。
    排除"呢"结尾的句子（"豆仔帮你盯着呢"不是问句）。
    """
    import re
    # 匹配: ?/？结尾 或 "吗/吧"结尾 → 真正的问题
    # 排除: "呢"结尾的陈述句 ("盯着呢""看着呢"等)
    sentence_pattern = re.compile(r'[^。！？\n]+(?:[？?]|[吗吧](?:[？?]|$))')
    matches = sentence_pattern.findall(answer)
    if matches:
        q = matches[-1].strip()
        return q if len(q) <= 120 else None
    return None


async def _compress_and_save(
    cid: str, conv_svc, prev_summary: str,
    last_query: str, last_answer: str, pending_question: str | None,
):
    """后台异步压缩对话历史并写入 context_snapshot。"""
    if not cid or not last_query:
        return
    try:
        from app.services.context_compressor import get_context_compressor
        compressor = get_context_compressor()
        result = await compressor.compress(
            prev_summary=prev_summary,
            last_query=last_query,
            last_answer=last_answer,
            pending_question=pending_question,
        )
        await conv_svc.aupdate_context_snapshot(cid, {
            "conversation_summary": result.get("summary", ""),
        })
    except Exception:
        pass  # 压缩失败不影响主链路


async def _build_recent_turns(cid, conv_svc, current_turn: dict) -> list[dict]:
    """追加当前轮，保留最近 3 轮摘要 (async — 在事件循环中直接 await)。"""
    try:
        snapshot = await conv_svc.get_context_snapshot(cid)
    except Exception:
        snapshot = {}
    turns = snapshot.get("recent_turns", [])
    if not isinstance(turns, list):
        turns = []
    turns.append(current_turn)
    return turns[-3:]


# ============================================================
# 辅助: 写入/读取聚焦商品到 conversation context_snapshot
# ============================================================
async def _write_focus_product(conv_svc, conversation_id: str, product):
    """问豆仔点击时锁定商品 → context_snapshot"""
    if not conv_svc or not conversation_id:
        return
    try:
        await conv_svc.set_focus_product(conversation_id, product)
    except Exception as e:
        logger.warning(f"Failed to write focus_product: {e}")


async def _read_focus_product(conv_svc, conversation_id: str) -> dict:
    """读取聚焦商品, 返回 {id,title,price,brand} 或空dict"""
    if not conv_svc or not conversation_id:
        return {}
    try:
        snapshot = await conv_svc.get_context_snapshot(conversation_id)
        fp = snapshot.get("focus_product", {})
        if fp:
            logger.info(f"Focus product read: {fp.get('product_id')} {fp.get('title','')[:30]}")
        return fp
    except Exception as e:
        logger.warning(f"Failed to read focus_product: {e}")
        return {}


async def _get_address(user_id: str) -> dict | None:
    """获取用户默认地址 — 兼容 PG (async) 和内存 (sync) 两种仓库"""
    if not user_id:
        return None
    try:
        from app.repositories.address_repo import get_address_repo
        repo = get_address_repo()
        if hasattr(repo, "_alist"):
            addrs = await repo._alist(user_id)
        else:
            addrs = repo.list(user_id)
        return next((a for a in addrs if a.get("is_default")), addrs[0] if addrs else None)
    except Exception as e:
        logger.warning(f"Failed to get address for {user_id}: {e}")
        return None


# ============================================================
# 路由
# ============================================================

@router.post("/stream")
async def recommend_stream(req: StreamRequest, raw_request: Request):

    async def gen() -> AsyncGenerator[str, None]:
        sid = req.session_id or str(_uuid.uuid4())[:8]
        uid = req.user_id or ""
        cid = req.conversation_id or ""
        msg = req.message or ""

        # ---- 判断意图 ----
        order_words = ["下单", "结算", "结账", "买单", "付款"]
        confirm_words = ["确认下单", "确认订单", "确认付款"]
        addr_words = ["修改地址", "改地址", "换地址"]
        clear_words = ["清空购物车"]
        all_shop_words = order_words + confirm_words + addr_words + clear_words
        is_shop = any(kw in msg for kw in all_shop_words)

        # ---- 初始化 conv_svc ----
        conv_svc = None
        try:
            from app.services.conversation_service import get_conversation_service
            conv_svc = get_conversation_service()
        except Exception as e:
            logger.warning(f"conv_svc init failed: {e}")

        # ================================================================
        # 下单流程 (独立于购物车)
        # ================================================================
        if is_shop:
            fp = await _read_focus_product(conv_svc, cid)
            fp_id = fp.get("product_id", "")
            fp_title = fp.get("title", "")
            fp_price = float(fp.get("price", 0))
            fp_brand = fp.get("brand", "")

            async def _yield_answer(text: str, actions: list | None = None):
                """SSE流式: 先逐字token, 再result, 最后done"""
                for ch in text:
                    yield _sse("token", json.dumps({"text": ch}, ensure_ascii=False))
                payload = {"answer": text, "products": [], "decision_results": [],
                           "shop_action": True, "harness_report": {}}
                if actions:
                    payload["actions"] = actions
                yield _sse("result", json.dumps(payload, ensure_ascii=False))
                yield _sse("done", "{}")

            # --- 确认下单 (必须在 order_words 之前, 因为"确认下单"包含"下单") ---
            if any(kw in msg for kw in confirm_words) or (msg.strip() == "确认" and len(msg.strip()) <= 3):
                if not fp_id:
                    async for e in _yield_answer("没有找到要下单的商品～"):
                        yield e
                    return
                addr = await _get_address(uid)
                if not addr:
                    async for e in _yield_answer("还没有收货地址～点下方按钮填写后再说「下单」就行！",
                                                 [{"type": "address_form", "label": "填写收货地址"}]):
                        yield e
                    return
                oid = f"ORD-{_uuid.uuid4().hex[:8].upper()}"
                text = (
                    f"🎉 下单成功！\n\n"
                    f"📋 订单号：{oid}\n"
                    f"🛒 商品：{fp_brand} {fp_title[:30]}\n"
                    f"💰 实付：¥{fp_price:.0f}\n"
                    f"📍 {addr.get('name','')} {addr.get('phone','')}\n"
                    f"   {addr.get('province','')}{addr.get('city','')}"
                    f"{addr.get('district','')} {addr.get('detail','')}\n"
                    f"⏱️ 预计2-3天送达\n\n"
                    f"感谢购买！还有什么需要帮忙的吗？"
                )
                async for e in _yield_answer(text):
                    yield e
                return

            # --- 下单 ---
            if any(kw in msg for kw in order_words):
                if not fp_id:
                    async for e in _yield_answer("请先去商品详情页点「问豆仔」，我帮你分析后再下单哦～"):
                        yield e
                    return

                addr = await _get_address(uid)
                addr_str = (
                    f"📍 {addr.get('name','')}  {addr.get('phone','')}\n"
                    f"   {addr.get('province','')}{addr.get('city','')}"
                    f"{addr.get('district','')} {addr.get('detail','')}"
                ) if addr else "📍 未设置收货地址"

                text = (
                    f"📦 订单确认\n\n"
                    f"  商品：{fp_brand} {fp_title[:40]}\n"
                    f"  价格：¥{fp_price:.0f}\n"
                    f"  数量：1件\n\n"
                    f"💰 合计：¥{fp_price:.0f}\n"
                    f"{addr_str}\n\n"
                    + ("确认下单吗？" if addr else "⚠️ 请先设置收货地址～")
                )
                act = (
                    [{"type": "quick_reply", "label": "确认下单"},
                     {"type": "address_form", "label": "修改地址"}]
                    if addr else
                    [{"type": "address_form", "label": "填写收货地址"}]
                )
                async for e in _yield_answer(text, act):
                    yield e
                return

            # --- 修改地址 ---
            if any(kw in msg for kw in addr_words):
                async for e in _yield_answer("好的～在下方填写新地址，填好后告诉我「下单」就行！",
                                             [{"type": "address_form", "label": "填写新地址"}]):
                    yield e
                return

            # --- 清空购物车 ---
            if any(kw in msg for kw in clear_words):
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    await get_cart_repo().aclear_cart(uid)
                    async for e in _yield_answer("✅ 购物车已清空～"):
                        yield e
                except Exception:
                    async for e in _yield_answer("清空失败，请去购物车页面手动操作～"):
                        yield e
                return

            # 兜底
            async for e in _yield_answer("好的～你可以对商品点「问豆仔」后说「下单」来直接结算哦！"):
                yield e
            return

        # ================================================================
        # 以下是原有的推荐/聚焦分析流程 (保持不变)
        # ================================================================
        import time as _time
        _t_total_start = _time.perf_counter()

        is_focused = (
            req.mode == "product_focused_analysis"
            and req.target_product_id
            and req.target_product_id.strip()
        )

        # P0: conversation
        try:
            conv_result = await conv_svc.aget_or_create(
                user_id=uid, session_id=sid, conversation_id=cid,
            )
            cid = conv_result["conversation_id"]
        except Exception:
            pass

        if cid:
            try:
                await conv_svc.aappend_user_message(
                    conversation_id=cid, user_id=uid,
                    session_id=sid, content=req.message,
                    image_url=req.image_url or "",
                )
            except Exception:
                pass

        # P2 + P4: FollowUpEngine + Profile 并行加载
        _t0 = _time.perf_counter()
        enriched_query = req.message
        followup_constraints = {}
        context_prompt = ""

        async def _run_followup():
            nonlocal enriched_query, followup_constraints
            try:
                from app.services.followup_engine import get_followup_engine
                engine = get_followup_engine()
                fu = engine.detect(conversation_id=cid, session_id=sid, current_query=req.message)
                if fu.get("is_follow_up") and fu.get("context_prompt"):
                    enriched_query = f"{req.message}\n\n{fu['context_prompt']}"
                if fu.get("updated_constraints"):
                    followup_constraints = fu["updated_constraints"]
                return fu
            except Exception:
                return {}

        async def _run_profile():
            try:
                if uid:
                    from app.services.user_profile_service import get_user_profile_service
                    return await get_user_profile_service().inject_profile_hints(
                        uid, query=req.message, enriched_query=req.message,
                        context_prompt="",
                    )
            except Exception:
                pass
            return {"enriched_query": req.message, "context_prompt": "", "avoid_tags": []}

        import asyncio as _asyncio
        follow_up, hints_result = await _asyncio.gather(_run_followup(), _run_profile())
        # 合并：FollowUp context_prompt + Profile context_prompt
        context_prompt = (follow_up.get("context_prompt", "") + "\n" + hints_result["context_prompt"]).strip()
        # 如果 FollowUp 改写了 query，保留改写版本；否则用 profile 增强版
        if enriched_query == req.message:
            enriched_query = hints_result["enriched_query"]
        logger.info(f"⏱ followup+profile: {(_time.perf_counter() - _t0)*1000:.0f}ms (parallel)")

        # P4: 对话提取检查 — 后台执行，不阻塞用户看到回复
        try:
            if uid:
                from app.services.user_profile_service import get_user_profile_service
                _svc = get_user_profile_service()
                if _svc.has_long_term_signal(req.message):
                    asyncio.create_task(_svc.parse_and_merge(uid, req.message))
        except Exception:
            pass

        try:
            target_analysis = None
            alternatives = []
            comparison = None
            cross_category = []

            if is_focused:
                target_pid = req.target_product_id.strip()
                from app.repositories.product_repo import get_product_repo
                repo = get_product_repo()
                target = repo.get_by_id(target_pid)

                if target:
                    # 锁定聚焦商品
                    await _write_focus_product(conv_svc, cid, target)

                    cat = target.category
                    sub = target.sub_category
                    rk = target.rag_knowledge

                    # Layer 1: 深度分析
                    review_summary = ""
                    if rk and rk.user_reviews:
                        ratings = [r.rating for r in rk.user_reviews]
                        avg_r = sum(ratings) / len(ratings)
                        pos = sum(1 for r in ratings if r >= 4)
                        review_summary = f"用户口碑: {avg_r:.1f}/5（{len(ratings)}条评论，{pos}条好评）"

                    faq_summary = ""
                    if rk and rk.official_faq:
                        topics = [f.question[:30] for f in rk.official_faq[:3]]
                        faq_summary = f"FAQ覆盖: {' / '.join(topics)}"

                    sku_summary = ""
                    if target.skus:
                        prices = [s.price for s in target.skus]
                        sku_summary = f"共{len(target.skus)}个规格，价格区间 ¥{min(prices):.0f}-¥{max(prices):.0f}"

                    cat_angles = {
                        "数码电子": "参数配置、兼容性、使用场景",
                        "美妆护肤": "成分功效、适用肤质、性价比",
                        "服饰运动": "材质舒适度、尺码适配、穿搭场景",
                        "食品饮料": "口味特点、健康程度、规格划算度",
                    }
                    angle = cat_angles.get(cat, "优缺点、性价比、是否值得买")

                    search_query = f"{target.title} {target.brand} {cat} {sub}"
                    analysis_prompt = (
                        f"请以导购身份深度分析「{target.title}」（{target.brand}，"
                        f"¥{target.base_price}，{cat}/{sub}）。\n"
                        f"分析角度：{angle}。\n"
                        f"数据参考：{review_summary}。{faq_summary}。{sku_summary}。\n"
                        f"描述：{rk.marketing_description[:300] if rk else ''}\n"
                        f"用户问：{req.message}\n"
                        f"请分点列出：优势/适用人群/注意事项/规格建议。控制在200字以内。"
                    )
                    if context_prompt:
                        analysis_prompt = analysis_prompt + "\n\n" + context_prompt

                    from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
                    prefill = WorkflowState(
                        user_query=search_query,
                        image_url=req.image_url,
                        constraints=Constraints(category=cat, sub_category=sub),
                        retrieval_plan=RetrievalPlan(
                            channels=["text", "review", "policy"],
                            category=cat, sub_category=sub, top_k=5,
                        ),
                    )
                    state = await run_workflow(
                        user_query=search_query,
                        image_url=req.image_url,
                        session_id=sid, user_id=uid,
                        conversation_id=cid,
                        enable_checkpoint=False,
                        prefill_state=prefill,
                        context_prompt=analysis_prompt,
                    )

                    # 确保目标商品在检索结果中
                    target_in_results = any(
                        p.get("product_id") == target_pid
                        for p in state.retrieved_products
                    )
                    if not target_in_results:
                        target_dict = {
                            "product_id": target.product_id,
                            "title": target.title,
                            "brand": target.brand,
                            "category": target.category,
                            "sub_category": target.sub_category,
                            "price": target.base_price,
                            "image_urls": [target.image_path] if target.image_path else [],
                            "rag_knowledge": target.rag_knowledge.model_dump() if target.rag_knowledge else {},
                        }
                        state.retrieved_products.insert(0, target_dict)
                        from app.agents.decision_agent import DecisionAgent
                        await DecisionAgent().execute(state)

                    # 聚焦商品得分拉满
                    for dr in state.decision_results:
                        if dr.get("product_id") == target_pid:
                            comp = dr.get("component_scores", {})
                            if "relevance" in comp:
                                comp["relevance"]["score"] = 1.0
                            if "scenario_fit" in comp:
                                comp["scenario_fit"]["score"] = 1.0
                            raw = sum(v["score"] * (v.get("weight") or 0) for v in comp.values())
                            dr["final_score"] = min(1.0, raw)
                            dr["display_score"] = round(raw * 10, 1)
                            dr["recommendation_level"] = "strong_recommend" if raw >= 0.80 else "recommended"
                            break

                    # 构建 target_analysis
                    target_dec = None
                    for dr in state.decision_results:
                        if dr.get("product_id") == target_pid:
                            target_dec = dr
                            break

                    if target_dec:
                        strengths = []
                        if rk and rk.user_reviews:
                            ratings = [r.rating for r in rk.user_reviews]
                            avg_r = sum(ratings) / len(ratings)
                            if avg_r >= 4.0:
                                strengths.append(f"用户口碑好({avg_r:.1f}/5)")
                        if rk and rk.official_faq:
                            strengths.append(f"FAQ覆盖{len(rk.official_faq)}个问题")
                        faq_questions = [f.question for f in rk.official_faq[:5]] if rk and rk.official_faq else []
                        component_scores = target_dec.get("component_scores", {})
                        target_analysis = {
                            "product_id": target_pid,
                            "title": target.title,
                            "brand": target.brand,
                            "price": target.base_price,
                            "category": cat,
                            "sub_category": sub,
                            "recommendation_level": target_dec.get("recommendation_level", ""),
                            "display_score": target_dec.get("display_score", 0),
                            "evidence_confidence": target_dec.get("evidence_confidence", 0),
                            "suitable_for": [s for s in strengths[:3] if s],
                            "strengths": [s for s in strengths[:3] if s],
                            "risks": target_dec.get("risk_factors", [])[:3],
                            "faq_questions": faq_questions,
                            "review_summary": {
                                "count": len(ratings),
                                "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
                                "positive_ratio": round(sum(1 for r in ratings if r >= 4) / len(ratings) * 100) if ratings else 0,
                            } if ratings else None,
                            "sku_advice": sku_summary,
                            "component_scores": {k: v for k, v in list(component_scores.items())[:7]},
                            "support_evidence_ids": target_dec.get("support_evidence_ids", []),
                        }

                    # 同类对比 + 场景拓展 (略,保持不变)
                    alt_products = [p for p in state.retrieved_products if p.get("product_id") != target_pid][:3]
                    alt_decisions = [d for d in state.decision_results if d.get("product_id") != target_pid][:3]
                    for ap, ad in zip(alt_products, alt_decisions):
                        alternatives.append({
                            "product_id": ap.get("product_id"),
                            "title": ap.get("title", ""),
                            "brand": ap.get("brand", ""),
                            "price": ap.get("price", 0),
                            "display_score": ad.get("display_score", 0),
                            "recommendation_level": _LEVEL_CN.get(ad.get("recommendation_level", ""), ad.get("recommendation_level", "")),
                        })
                    if target_analysis and alternatives:
                        dims = ["价格", "推荐分", "推荐等级"]
                        tgt_vals = [
                            f"¥{target.base_price:.0f}",
                            f"{target_dec.get('display_score',0)}/10",
                            _LEVEL_CN.get(target_dec.get('recommendation_level',''), target_dec.get('recommendation_level','')),
                        ]
                        alt_rows = []
                        for a in alternatives:
                            alt_rows.append([f"¥{a['price']:.0f}", f"{a['display_score']}/10", a["recommendation_level"]])
                        cs = target_dec.get("component_scores", {})
                        for key, label in [("user_sat","用户口碑"), ("value_score","性价比"), ("spec_quality","规格品质")]:
                            if cs.get(key, {}).get("score", 0) > 0:
                                dims.append(label)
                                tgt_vals.append(f"{cs[key]['score']*10:.1f}/10")
                                for idx, ad in enumerate(alt_decisions):
                                    acs = ad.get("component_scores", {})
                                    if idx < len(alt_rows):
                                        alt_rows[idx].append(f"{acs.get(key,{}).get('score',0)*10:.1f}/10")
                        comparison = {
                            "dimensions": dims,
                            "target_values": tgt_vals,
                            "alternative_values": alt_rows,
                        }

                else:
                    from app.schemas.workflow import WorkflowState as Ws
                    state = Ws(
                        user_query=req.message,
                        answer="抱歉～我没找到这件商品的信息 😅 你可以直接告诉我你想买什么，我帮你推荐！",
                        retrieved_products=[], decision_results=[],
                    )
            else:
                # 构建 prefill (FollowUpEngine 检测到的追问约束)
                _t_wf = _time.perf_counter()
                prefill = _build_constraint_prefill(followup_constraints) if followup_constraints else None
                state = await run_workflow(
                    user_query=enriched_query, image_url=req.image_url,
                    session_id=sid, user_id=uid, conversation_id=cid,
                    enable_checkpoint=False, prefill_state=prefill,
                    context_prompt=context_prompt,
                )
                logger.info(f"⏱ workflow: {(_time.perf_counter() - _t_wf)*1000:.0f}ms (total: {(_time.perf_counter() - _t_total_start)*1000:.0f}ms)")
                if hasattr(state, 'timing') and state.timing:
                    logger.info(f"⏱ breakdown: {json.dumps(state.timing, ensure_ascii=False, default=str)}")

            answer = state.answer or "抱歉，暂时无法回答您的问题。"

            # P3: 购买意向检测
            if is_focused and target:
                purchase_signals = 1
                positive_words = ["不错", "很好", "可以", "就这个", "买", "下单", "要了", "行", "好"]
                if any(w in req.message for w in positive_words):
                    purchase_signals += 1
                if alternatives:
                    purchase_signals += 1
                if purchase_signals >= 2:
                    answer += f"\n\n看起来你对「{target.title[:20]}」挺满意的～要不要我帮你直接下单？回复「下单」就行！"

            # SSE流式输出
            for i, ch in enumerate(answer):
                if await raw_request.is_disconnected():
                    break
                yield _sse("token", json.dumps({"text": ch}, ensure_ascii=False))
                await asyncio.sleep(0.03)

            result = {
                "session_id": sid,
                "conversation_id": cid,
                "answer": answer,
                "products": _safe_dump(state.retrieved_products or []),
                "decision_results": _safe_dump(state.decision_results or []),
                "evidence_list": _safe_dump(state.evidence_list or []),
                "trace_steps": _safe_dump(state.trace_steps or []),
                "harness_report": _safe_dump(state.harness_report or {}),
                "used_memories": _safe_dump(state.used_memories or []),
                "blocked_memories": _safe_dump(state.blocked_memories or []),
                "memory_trace": _safe_dump(state.memory_trace or {}),
                "needs_clarification": state.needs_clarification,
                "clarification_question": state.clarification_question,
                "clarification_options": _safe_dump(state.clarification_options or []),
                "timing": _safe_dump(state.timing or {}),
                "target_product_analysis": target_analysis,
                "alternative_products": alternatives,
                "comparison_table": comparison,
                "cross_category": cross_category,
            }
            yield _sse("result", json.dumps(result, ensure_ascii=False, default=str))
            yield _sse("done", json.dumps({"finish_reason": "stop"}))

            if cid:
                try:
                    # 结构化商品列表 (供 FollowUpEngine 做指代解析)
                    product_ids = []
                    structured_products = []
                    for p in (state.retrieved_products or [])[:10]:
                        pid = p.get("product_id", "")
                        if pid:
                            product_ids.append(pid)
                            structured_products.append({
                                "product_id": pid,
                                "title": p.get("title", "")[:60],
                                "brand": p.get("brand", ""),
                                "price": p.get("price", 0),
                            })

                    await conv_svc.aappend_assistant_message(
                        conversation_id=cid, user_id=uid,
                        session_id=sid, content=answer,
                        product_refs=product_ids,
                    )

                    # 提取豆仔回复中的问题 (供下一轮 Router 做问答链匹配)
                    pending_question = _extract_question(answer)

                    # 保留最近 N 轮对话摘要
                    recent_turns = await _build_recent_turns(cid, conv_svc, {
                        "user_query": req.message,
                        "assistant_answer": answer[:300],
                        "product_ids": product_ids,
                    })

                    # 持久化 Router 检测到的品类，供下一轮 FollowUpEngine 继承
                    snapshot_update = {
                        "last_query": req.message,
                        "last_answer": answer[-500:] if len(answer) > 500 else answer,
                        "last_products": structured_products,
                        "pending_question": pending_question,
                        "recent_turns": recent_turns,
                    }
                    if hasattr(state, 'constraints') and state.constraints:
                        c = state.constraints
                        cur_turn = {}
                        if c.category:
                            cur_turn["category"] = c.category
                        if c.sub_category:
                            cur_turn["sub_category"] = c.sub_category
                        if c.budget_max:
                            cur_turn["budget_max"] = c.budget_max
                        if c.scenario:
                            cur_turn["scenario"] = c.scenario
                        if cur_turn:
                            snapshot_update["current_turn"] = cur_turn
                    await conv_svc.aupdate_context_snapshot(cid, snapshot_update)

                    # P4: 异步上下文压缩 — 不阻塞 SSE，后台增量更新 conversation_summary
                    try:
                        prev_summary = (conv_svc.get_context_snapshot_sync(cid) or {}).get(
                            "conversation_summary", ""
                        ) or ""
                        asyncio.create_task(
                            _compress_and_save(cid, conv_svc, prev_summary,
                                               req.message, answer, pending_question)
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

        except asyncio.CancelledError:
            logger.info(f"SSE cancelled: {sid}")
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield _sse("error", json.dumps({"message": str(e)}))
            yield _sse("done", json.dumps({"finish_reason": "error"}))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _safe_dump(obj):
    """递归转换 Pydantic model / 非标准对象为可 JSON 序列化的 dict"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_dump(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return _safe_dump(obj.model_dump())
    if hasattr(obj, "dict"):
        return _safe_dump(obj.dict())
    return str(obj)


def _build_constraint_prefill(constraints: dict):
    """将 FollowUpEngine 的 constraints dict 转为 WorkflowState prefill"""
    if not constraints:
        return None
    from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
    return WorkflowState(
        constraints=Constraints(
            category=constraints.get("category"),
            sub_category=constraints.get("sub_category"),
            budget_max=constraints.get("budget_max"),
            budget_min=constraints.get("budget_min"),
        ),
        retrieval_plan=RetrievalPlan(
            channels=["text", "review", "policy"],
            category=constraints.get("category"),
            sub_category=constraints.get("sub_category"),
        ) if constraints.get("category") else None,
    )
