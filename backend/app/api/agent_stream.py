"""SSE 流式端点 — 正常推荐 / 商品聚焦分析 / 直接下单"""
import asyncio, json, logging, uuid as _uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.workflow.graph import run_workflow
from app.core.identity import Actor, resolve_public_actor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["stream"])

# 后台持久化任务引用持有（防 GC 提前回收 create_task）
_BG_TASKS: set = set()


class StreamRequest(BaseModel):
    session_id: str = ""
    user_id: str = ""
    conversation_id: str = ""
    message: str = ""
    image_url: str | None = None
    mode: str = "normal_recommend"
    target_product_id: str | None = None
    allow_same_category_comparison: bool = False
    fast_mode: bool = False  # 快速回答：跳过LLM，直接模板回复（等价 exec_mode="lite"）
    exec_mode: str = ""  # P2-1 执行档位 lite/standard/max（max=动态编排按请求灰度）；与业务场景 mode 字段无关
    deep_think: bool = False  # 深度思考：OmniAgent Loop 预算 3→8 轮（Phase 7）


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
    """从欧米回复中提取问句，供下一轮 Router 做问答链匹配。

    只匹配真正的问句 — 以？结尾，或以"吗/吧"结尾的疑问句。
    排除"呢"结尾的句子（"欧米帮你盯着呢"不是问句）。
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


async def _generate_title(cid: str, conv_svc, first_query: str, first_answer: str):
    """后台异步生成对话标题。LLM 失败时降级为首条消息前15字。"""
    if not cid or not first_query:
        return
    title = ""
    try:
        from app.core.config import MOCK_MODE
        if not MOCK_MODE:
            from app.model_gateway.gateway import get_model_gateway
            from app.prompts.api_prompts import build_title_prompt
            gateway = get_model_gateway()
            prompt = build_title_prompt(first_query, first_answer)
            title = (await gateway.chat("chat_generation", prompt)).strip()
            if title and len(title) > 15:
                title = title[:15]  # 截断过长的标题
    except Exception:
        pass
    # 降级：首条消息截取
    if not title:
        title = first_query.strip()[:15]
    if title:
        await conv_svc.aupdate_context_snapshot(cid, {"title": title})
        # 同时更新 conversations 表的 title 字段
        try:
            from app.core.database import get_session_sync
            from app.models.conversation import ConversationModel
            from sqlalchemy import update
            factory = get_session_sync()
            async with factory() as session:
                await session.execute(
                    update(ConversationModel)
                    .where(ConversationModel.conversation_id == cid)
                    .values(title=title)
                )
                await session.commit()
        except Exception:
            pass


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
# 辅助: 写入聚焦商品到 conversation context_snapshot（读取/地址解析已收敛到 ShopActionAgent）
# ============================================================
async def _write_focus_product(conv_svc, conversation_id: str, product):
    """问欧米点击时锁定商品 → context_snapshot"""
    if not conv_svc or not conversation_id:
        return
    try:
        await conv_svc.set_focus_product(conversation_id, product)
    except Exception as e:
        logger.warning(f"Failed to write focus_product: {e}")


# ============================================================
# 路由
# ============================================================

@router.post("/stream")
async def recommend_stream(req: StreamRequest, raw_request: Request,
                           actor: Actor = Depends(resolve_public_actor)):

    async def gen() -> AsyncGenerator[str, None]:
        sid = req.session_id or str(_uuid.uuid4())[:8]
        uid = actor.user_id
        cid = req.conversation_id or ""
        msg = req.message or ""

        # ---- 判断意图: 购物操作关键词（仅门控进入 Tool 链，实际路由在 ShopActionAgent 内） ----
        order_words = ["下单", "结算", "结账", "买单", "付款"]
        confirm_words = ["确认下单", "确认订单", "确认付款"]
        addr_words = ["修改地址", "改地址", "换地址"]
        clear_words = ["清空购物车"]
        cart_show_words = ["购物车有什么", "看看购物车", "看购物车"]
        cart_remove_words = ["删除第", "去掉第", "移除第"]
        cart_qty_words = ["数量改成", "数量改为", "数量改成第", "数量改为第"]
        cart_add_words = ["加入购物车", "加到购物车", "加进购物车", "加购", "全部加入"]
        # Phase 2b: 订单闭环 & 库存（与 ShopActionAgent 关键词表保持一致，否则新工具不可达）
        order_manage_words = ["我的订单", "订单列表", "查看订单", "看订单", "订单详情",
                              "取消订单", "取消第", "物流", "查物流", "追踪",
                              "支付订单", "去支付", "支付第", "付款第",
                              "有货吗", "库存", "还有货", "缺货吗"]
        # Phase 6-B3: 偏好 & 会话（同样与 ShopActionAgent 保持一致）
        pref_conv_words = ["我的偏好", "偏好列表", "查看偏好", "记住了什么", "删除偏好", "删掉偏好",
                           "记住我", "记一下我", "以后推荐", "以后都", "别再推", "不要推荐",
                           "聊了什么", "刚才说了什么", "对话历史", "聊天记录",
                           "重新开始", "清空上下文", "重置对话",
                           "写个文案", "写文案", "种草文案", "帮我种草"]
        all_shop_words = (order_words + confirm_words + addr_words + clear_words
                          + cart_show_words + cart_remove_words + cart_qty_words + cart_add_words
                          + order_manage_words + pref_conv_words)
        is_shop = any(kw in msg for kw in all_shop_words)

        # ---- 初始化 conv_svc ----
        conv_svc = None
        try:
            from app.services.conversation_service import get_conversation_service
            conv_svc = get_conversation_service()
        except Exception as e:
            logger.warning(f"conv_svc init failed: {e}")
        
        # P0-3: 会话创建/用户消息落库上移到购物块之前——
        # shop 轮次同样入历史，且首条消息即购物动作时 pending 快照有真实 cid 可写
        if conv_svc:
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
        
        # 读取 pending SKU 选择（用户可能正在选规格）
        _pending_sku = {}
        try:
            if conv_svc and cid:
                snap = await conv_svc.get_context_snapshot(cid)
                _pending_sku = (snap or {}).get("pending_sku_product", {}) or {}
        except Exception:
            pass
        
        # P1-3: 复合指令（“看订单然后推荐类似的”）不进购物块——
        # 交给推荐工作流（动态图/LLM Planner 可编排 tool 步 + 检索），避免关键词门控截胡后半句
        _is_compound = False
        if is_shop and not _pending_sku:
            try:
                from app.framework.orchestration.planner import _is_complex
                _is_compound = _is_complex(msg)[0]
            except Exception:
                _is_compound = False

        # ================================================================
        # 深度思考模式（spec: docs/specs/omni-harness）：deep_think=true 时 OmniAgent
        # ReAct Loop 全权接管（跳过购物关键词门控，LLM 自主决策调工具）；
        # 默认链路仍走 pipeline。极速命令/规格选择/聚焦分析不进 Loop；
        # LLM 异常时落回下方既有链路兜底。
        # ================================================================
        from app.core.config import ENABLE_AGENT_LOOP

        _FAST_COMMANDS = {"看看购物车", "清空购物车", "我的订单", "我的偏好", "重新开始"}
        if (ENABLE_AGENT_LOOP and req.deep_think and req.mode != "product_focused_analysis"
                and not _pending_sku and msg.strip() not in _FAST_COMMANDS):
            from app.agents.omni_agent import OmniAgent
            from app.framework.blackboard import Blackboard, reset_current_board, set_current_board
            from app.framework.tools import ToolContext as _TC
            from app.schemas.workflow import WorkflowState as _WS

            _loop_state = _WS(session_id=sid, user_id=uid, conversation_id=cid, user_query=msg)
            _loop_ctx = _TC(user_id=uid, session_id=sid, conversation_id=cid,
                            args_raw=msg, state=_loop_state)
            _bb_token = set_current_board(Blackboard())
            _loop_ok = False
            _loop_actions: list = []  # 工具产出的交互动作（如 sku_option 规格选择按钮）
            try:
                async for _ev in OmniAgent().run_events(msg, _loop_ctx, req.deep_think):
                    _et = _ev.get("type")
                    if _et == "status":
                        yield _sse("status", json.dumps({"text": _ev["text"]}, ensure_ascii=False))
                    elif _et == "token":
                        # 收口轮 chat_stream 真流式（spec D2）：逐 token 直转发
                        if await raw_request.is_disconnected():
                            break
                        yield _sse("token", json.dumps({"text": _ev["text"]}, ensure_ascii=False))
                    elif _et == "tool_result":
                        # 收集工具产出的 actions（spec §4）——深度思考分支以前不透传，
                        # 导致多规格商品加购时规格选择按钮消失，只能纯对话选
                        for _a in (_ev.get("actions") or []):
                            if isinstance(_a, dict) and _a not in _loop_actions:
                                _loop_actions.append(_a)
                    elif _et == "answer" and _ev.get("content"):
                        # 自然结束轮的全文终稿：按块快速回放
                        _txt = _ev["content"]
                        for _i in range(0, len(_txt), 12):
                            if await raw_request.is_disconnected():
                                break
                            yield _sse("token", json.dumps({"text": _txt[_i:_i + 12]}, ensure_ascii=False))
                            await asyncio.sleep(0.005)
                _loop_ok = True
            except Exception as e:  # noqa: BLE001 — LLM 异常降级到既有 workflow
                logger.warning(f"agent loop failed, falling back to workflow: {e}")
            finally:
                reset_current_board(_bb_token)

            if _loop_ok:
                # 终稿权在 Loop（spec D2）：state.answer 已由 conclude/收口轮写入；
                # 仅在 Loop 零产出时降级 ResponseAgent 统稿（兼容兜底）
                from app.workflow.graph import get_response_agent, get_response_guard
                _answer = (_loop_state.answer or "").strip()
                if not _answer:
                    _full = ""
                    try:
                        async for _tok in get_response_agent().generate_stream(_loop_state):
                            if await raw_request.is_disconnected():
                                break
                            _full += _tok
                            yield _sse("token", json.dumps({"text": _tok}, ensure_ascii=False))
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"loop fallback generation failed: {e}")
                    _answer = _full.strip() or "抱歉，暂时无法回答您的问题。"
                    if not _full:
                        yield _sse("token", json.dumps({"text": _answer}, ensure_ascii=False))
                _loop_state.answer = _answer
                try:
                    get_response_guard().check(_loop_state)
                except Exception:  # noqa: BLE001
                    pass
                _payload = {
                    "session_id": sid, "conversation_id": cid, "answer": _answer,
                    "products": _safe_dump(_slim_products(_order_by_cited(
                        _loop_state.retrieved_products or [], _loop_state.answer_cited_pids or []))),
                    "decision_results": _safe_dump(_loop_state.decision_results or []),
                    "evidence_list": _safe_dump(_slim_evidence(
                        _loop_state.evidence_list or [], _loop_state.answer_cited_pids or [],
                        _loop_state.retrieved_products or [])),
                    "trace_steps": _safe_dump(_loop_state.trace_steps or []),
                    "skill_executions": _safe_dump(_loop_state.skill_executions or []),
                    "harness_report": _safe_dump(_loop_state.harness_report or {}),
                    "agent_loop": True, "deep_think": req.deep_think,
                }
                if _loop_actions:
                    _payload["actions"] = _safe_dump(_loop_actions)
                yield _sse("result", json.dumps(_payload, ensure_ascii=False, default=str))
                yield _sse("done", json.dumps({"finish_reason": "stop"}))
                # 持久化：助手消息 + last_products 快照（供下一轮指代）
                if conv_svc and cid:
                    try:
                        await conv_svc.aappend_assistant_message(
                            conversation_id=cid, user_id=uid, session_id=sid, content=_answer)
                        _structured = [{"product_id": p.get("product_id", ""),
                                        "title": p.get("title", "")[:60],
                                        "brand": p.get("brand", ""),
                                        "price": p.get("price", 0)}
                                       for p in (_loop_state.retrieved_products or [])[:10]
                                       if p.get("product_id")]
                        _snap_upd = {"last_query": msg}
                        if _structured:
                            _snap_upd["last_products"] = _structured
                        await conv_svc.aupdate_context_snapshot(cid, _snap_upd)
                    except Exception:  # noqa: BLE001
                        pass
                return
            # Loop 失败 → 继续落入下方既有链路（购物门控 / workflow）
        
        # ================================================================
        # 购物操作流程 (加购 / 购物车管理 / 下单)
        # ================================================================
        if (is_shop or _pending_sku) and not _is_compound:
            async def _yield_answer(text: str, actions: list | None = None):
                """SSE流式: 按块快速回放, 再 result, 最后 done"""
                for _i in range(0, len(text), 12):
                    yield _sse("token", json.dumps({"text": text[_i:_i + 12]}, ensure_ascii=False))
                    await asyncio.sleep(0.005)
                payload = {"answer": text, "products": [], "decision_results": [],
                           "shop_action": True, "harness_report": {},
                           "conversation_id": cid}
                if actions:
                    payload["actions"] = actions
                yield _sse("result", json.dumps(payload, ensure_ascii=False))
                yield _sse("done", "{}")
        
            # ---- Tool 链: 全部购物动作委派给 ShopActionAgent（legacy if/elif 已随灰度收尾删除） ----
            from app.core.config import ENABLE_TOOL_ROUTER
            if ENABLE_TOOL_ROUTER:
                from app.agents.shop_action_agent import ShopActionAgent
                from app.framework.tools import ToolContext
                _ctx = ToolContext(user_id=uid, session_id=sid, conversation_id=cid, args_raw=msg)
                _res = await ShopActionAgent().handle(msg, _ctx)
                async for _e in _yield_answer(_res.message, _res.actions or None):
                    yield _e
                # P0-3: shop 回复同样写入会话历史（"聊了什么"可见）
                if conv_svc and cid and _res.message:
                    try:
                        await conv_svc.aappend_assistant_message(
                            conversation_id=cid, user_id=uid,
                            session_id=sid, content=_res.message,
                        )
                    except Exception:
                        pass
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

        # P2-2: 检索/生成前发中间态（前端未订阅的事件类型会静默忽略）
        yield _sse("status", json.dumps({"text": "欧米正在挑选好物…"}, ensure_ascii=False))

        # P0: conversation —— 已上移至购物块之前（P0-3），此处不再重复创建/落库

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
                # 预取 snapshot（async + 内存缓存），避免 detect 内部同步 PG 读阻塞事件循环
                _snap = None
                try:
                    if cid:
                        _snap = await conv_svc.get_context_snapshot(cid)
                except Exception:
                    _snap = None
                fu = engine.detect(conversation_id=cid, session_id=sid,
                                   current_query=req.message, snapshot=_snap)
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

        # ⭐ 对话式加购: FollowUpEngine 检测到 cart_intent → 直接加购
        if follow_up.get("follow_up_type") == "cart_intent":
            pid = follow_up.get("cart_intent_product_id", "")
            if pid:
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    from app.repositories.product_repo import get_product_repo
                    from app.schemas.cart import CartItemCreate
                    product = get_product_repo().get_by_id(pid)
                    if product:
                        await get_cart_repo().aadd_item(
                            CartItemCreate(product_id=pid, quantity=1), uid,
                            title=product.title, brand=product.brand,
                            price=product.base_price,
                            image_url=get_product_repo().resolve_image_url(product.product_id),
                            sku_label="",
                        )
                        title_short = (product.brand + " " + product.title)[:60]
                        # SSE 流式输出加购确认（按块快速回放）
                        answer = f"✅ 已把「{title_short}」加入购物车～"
                        for _i in range(0, len(answer), 12):
                            yield _sse("token", json.dumps({"text": answer[_i:_i + 12]}, ensure_ascii=False))
                            await asyncio.sleep(0.005)
                        yield _sse("result", json.dumps({
                            "session_id": sid, "conversation_id": cid,
                            "answer": answer, "products": [], "decision_results": [],
                            "shop_action": True, "harness_report": {},
                        }, ensure_ascii=False))
                        yield _sse("done", json.dumps({"finish_reason": "stop"}))
                        return
                except Exception as e:
                    logger.warning(f"cart_intent add failed: {e}")
                    # 加购失败不阻塞，降级走正常推荐流程

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
                        topics = [f.question[:50] for f in rk.official_faq[:3]]
                        faq_summary = f"FAQ覆盖: {' / '.join(topics)}"

                    sku_summary = ""
                    if target.skus:
                        prices = [s.price for s in target.skus]
                        sku_summary = f"共{len(target.skus)}个规格，价格区间 ¥{min(prices):.0f}-¥{max(prices):.0f}"

                    from app.prompts.api_prompts import build_focused_analysis_prompt, get_analysis_angle
                    angle = get_analysis_angle(cat)
                    
                    search_query = f"{target.title} {target.brand} {cat} {sub}"
                    analysis_prompt = build_focused_analysis_prompt(
                        title=target.title, brand=target.brand,
                        price=target.base_price, cat=cat, sub=sub,
                        review_summary=review_summary, faq_summary=faq_summary,
                        sku_summary=sku_summary,
                        description=rk.marketing_description[:300] if rk else "",
                        message=req.message,
                    )
                    if context_prompt:
                        analysis_prompt = analysis_prompt + "\n\n" + context_prompt

                    from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
                    profile_avoid = hints_result.get("avoid_tags") or []
                    prefill = WorkflowState(
                        user_query=search_query,
                        image_url=req.image_url,
                        constraints=Constraints(category=cat, sub_category=sub,
                                                exclude_tags=profile_avoid),
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
                        fast_mode=req.fast_mode,
                        mode=req.exec_mode,
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
                profile_avoid = hints_result.get("avoid_tags") or []
                prefill = _build_constraint_prefill(followup_constraints, profile_avoid)
                # 真流式：no_response 图只跑到 decision，回答由下方 generate_stream 边生成边推
                state = await run_workflow(
                    user_query=enriched_query, image_url=req.image_url,
                    session_id=sid, user_id=uid, conversation_id=cid,
                    enable_checkpoint=False, prefill_state=prefill,
                    context_prompt=context_prompt,
                    no_response=True,
                    fast_mode=req.fast_mode,
                    mode=req.exec_mode,
                )
                logger.info(f"⏱ workflow: {(_time.perf_counter() - _t_wf)*1000:.0f}ms (total: {(_time.perf_counter() - _t_total_start)*1000:.0f}ms)")
                if hasattr(state, 'timing') and state.timing:
                    logger.info(f"⏱ breakdown: {json.dumps(state.timing, ensure_ascii=False, default=str)}")

            answer = state.answer or ""

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

            # SSE 输出：普通推荐走真流式（LLM token 产出即转发）；
            # 聚焦分析等已持有全文的场景按块快速回放（不再逐字 sleep 30ms）
            if not is_focused and not answer:
                _t_resp = _time.perf_counter()
                from app.workflow.graph import get_response_agent, get_response_guard
                _full = ""
                try:
                    async for _tok in get_response_agent().generate_stream(state):
                        if await raw_request.is_disconnected():
                            break
                        _full += _tok
                        yield _sse("token", json.dumps({"text": _tok}, ensure_ascii=False))
                except Exception as e:
                    logger.warning(f"stream generation failed: {e}")
                answer = _full.strip() or "抱歉，暂时无法回答您的问题。"
                if not _full:
                    yield _sse("token", json.dumps({"text": answer}, ensure_ascii=False))
                state.answer = answer
                state.timing["response_ms"] = round((_time.perf_counter() - _t_resp) * 1000)
                try:
                    get_response_guard().check(state)
                except Exception:
                    pass
            else:
                answer = answer or "抱歉，暂时无法回答您的问题。"
                _CHUNK = 12
                for _i in range(0, len(answer), _CHUNK):
                    if await raw_request.is_disconnected():
                        break
                    yield _sse("token", json.dumps({"text": answer[_i:_i + _CHUNK]}, ensure_ascii=False))
                    await asyncio.sleep(0.005)

            result = {
                "session_id": sid,
                "conversation_id": cid,
                "answer": answer,
                "products": _safe_dump(_slim_products(_order_by_cited(
                    state.retrieved_products or [], state.answer_cited_pids or []))),
                "decision_results": _safe_dump(state.decision_results or []),
                "evidence_list": _safe_dump(_slim_evidence(
                    state.evidence_list or [], state.answer_cited_pids or [],
                    state.retrieved_products or [])),
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
                # 收尾持久化整体后台化 — done 已发，不再占用 SSE 连接时间
                _persist_state, _persist_answer = state, answer

                async def _persist_turn():
                    try:
                        # 结构化商品列表 (供 FollowUpEngine 做指代解析)
                        product_ids = []
                        structured_products = []
                        for p in (_persist_state.retrieved_products or [])[:10]:
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
                            session_id=sid, content=_persist_answer,
                            product_refs=product_ids,
                        )

                        # 提取欧米回复中的问题 (供下一轮 Router 做问答链匹配)
                        pending_question = _extract_question(_persist_answer)

                        # 保留最近 N 轮对话摘要
                        recent_turns = await _build_recent_turns(cid, conv_svc, {
                            "user_query": req.message,
                            "assistant_answer": _persist_answer[:300],
                            "product_ids": product_ids,
                        })

                        # 持久化 Router 检测到的品类，供下一轮 FollowUpEngine 继承
                        snapshot_update = {
                            "last_query": req.message,
                            "last_answer": _persist_answer[-500:] if len(_persist_answer) > 500 else _persist_answer,
                            "last_products": structured_products,
                            "pending_question": pending_question,
                            "recent_turns": recent_turns,
                        }
                        if hasattr(_persist_state, 'constraints') and _persist_state.constraints:
                            c = _persist_state.constraints
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

                        # P4: 异步上下文压缩 — 后台增量更新 conversation_summary
                        snap = await conv_svc.get_context_snapshot(cid) or {}
                        prev_summary = snap.get("conversation_summary", "") or ""
                        await _compress_and_save(cid, conv_svc, prev_summary,
                                                 req.message, _persist_answer, pending_question)
                        # 首次对话生成标题
                        if not snap.get("title", ""):
                            await _generate_title(cid, conv_svc, req.message, _persist_answer[:200])
                    except Exception:
                        pass

                _task = asyncio.create_task(_persist_turn())
                _BG_TASKS.add(_task)
                _task.add_done_callback(_BG_TASKS.discard)

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


def _order_by_cited(products: list, cited_pids: list) -> list:
    """按回答引用集置顶商品（spec §3）。

    自然语言回答只基于前 N 个候选生成，而列表可能回传 5-20 个——
    不置顶就会出现"回答讲 A/B、卡片列 C/D/E"。引用零时原序返回。
    未被引用的商品标 beyond_answer=True（前端可弱化展示）。
    """
    if not products or not cited_pids:
        return products
    by_pid = {}
    for p in products:
        if isinstance(p, dict) and p.get("product_id"):
            by_pid[p["product_id"]] = p
    head = [by_pid[pid] for pid in cited_pids if pid in by_pid]
    head_ids = {p.get("product_id") for p in head}
    tail = []
    for p in products:
        if not isinstance(p, dict) or p.get("product_id") in head_ids:
            continue
        q = dict(p)
        q["beyond_answer"] = True
        tail.append(q)
    return head + tail


# 商品卡下发白名单：前端商品卡 + 推理面板实际读取的字段（rag_knowledge 前端零消费，
# 详情页走 api.getProduct 独立拉取，故不下发；实测每卡省 ~4.3KB）
_CARD_KEEP = frozenset({
    "product_id", "title", "brand", "category", "sub_category", "price",
    "image_urls", "skus", "description", "score", "evidence_ids",
    "variant_count", "variant_product_ids", "beyond_answer",
    "reranker_score", "relevance_score", "avg_rating", "review_count",
})
_DESC_MAX = 120
_EVIDENCE_CONTENT_MAX = 140
_EVIDENCE_MAX = 20


def _slim_products(products: list) -> list:
    """SSE 出口商品卡瘦身（spec §1）：白名单裁字段 + description 截断。

    只在序列化出口做减法，不改 state 内对象（返回新 dict）。rag_knowledge 前端
    从不读取，是 result 帧最大冗余（~4.3KB/卡）。
    """
    slimmed = []
    for p in products or []:
        if not isinstance(p, dict):
            slimmed.append(p)
            continue
        q = {k: v for k, v in p.items() if k in _CARD_KEEP}
        desc = q.get("description")
        if isinstance(desc, str) and len(desc) > _DESC_MAX:
            q["description"] = desc[:_DESC_MAX]
        slimmed.append(q)
    return slimmed


def _slim_evidence(evidence_list: list, cited_pids: list, products: list) -> list:
    """SSE 出口证据裁剪（spec §2）：按展示商品过滤 + content 截断 + 条数上限。

    保留 answer_cited_pids 与实际下发商品对应的证据；content 截断至前端展示长度；
    上限对齐前端 EvidenceView 的 slice(0,20)。不改 state 内对象。
    """
    ev = evidence_list or []
    keep_pids = set(cited_pids or [])
    for p in products or []:
        if isinstance(p, dict) and p.get("product_id"):
            keep_pids.add(p["product_id"])
    out = []
    for e in ev:
        if not isinstance(e, dict):
            continue
        # 有归属商品的证据按展示集过滤；无 product_id 的通用证据保留
        pid = e.get("product_id")
        if keep_pids and pid and pid not in keep_pids:
            continue
        content = e.get("content")
        item = {
            "evidence_id": e.get("evidence_id"),
            "source_type": e.get("source_type"),
            "source_id": e.get("source_id"),
            "product_id": pid,
            "confidence": e.get("confidence"),  # 前端展示可信度，漏保留会出 NaN%
            "content": content[:_EVIDENCE_CONTENT_MAX] if isinstance(content, str) else content,
        }
        out.append(item)
        if len(out) >= _EVIDENCE_MAX:
            break
    return out


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


def _build_constraint_prefill(constraints: dict, avoid_tags: list | None = None):
    """将 FollowUpEngine 的 constraints dict + profile avoid_tags 转为 WorkflowState prefill"""
    if not constraints and not avoid_tags:
        return None
    from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
    c = constraints or {}
    merged_avoid = list(set((c.get("exclude_tags") or []) + (avoid_tags or [])))
    return WorkflowState(
        constraints=Constraints(
            category=c.get("category"),
            sub_category=c.get("sub_category"),
            budget_max=c.get("budget_max"),
            budget_min=c.get("budget_min"),
            exclude_tags=merged_avoid,
        ),
        retrieval_plan=RetrievalPlan(
            channels=["text", "review", "policy"],
            category=c.get("category"),
            sub_category=c.get("sub_category"),
        ),
    )
