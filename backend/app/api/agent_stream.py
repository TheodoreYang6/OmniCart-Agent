"""SSE 流式端点 — 正常推荐 / 商品聚焦分析 / 直接下单"""

import asyncio, json, logging, uuid as _uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.workflow.graph import run_workflow
from app.core.identity import Actor, require_user, resolve_public_actor
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["stream"])

# 后台持久化任务引用持有（防 GC 提前回收 create_task）
_BG_TASKS: set = set()

_STREAM_CHUNK_SIZE = 24
_STREAM_CHUNK_DELAY_SECONDS = 0.01


class StreamRequest(BaseModel):
    session_id: str = ""
    user_id: str = ""
    conversation_id: str = ""
    message: str = ""
    image_url: str | None = None
    # normal_recommend | product_focused_analysis | same_category_comparison.
    # Comparison is an explicit product action; do not infer it from free text.
    mode: str = "normal_recommend"
    target_product_id: str | None = None
    allow_same_category_comparison: bool = False
    fast_mode: bool = False  # 快速回答：跳过LLM，直接模板回复（等价 exec_mode="lite"）
    exec_mode: str = ""  # P2-1 执行档位 lite/standard/max（max=动态编排按请求灰度）；与业务场景 mode 字段无关
    deep_think: bool = False  # 深度思考：走 max 档 ReAct 图（受控 Plan-Execute）
    cart_payment: bool = False


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


_STAGE_TEXT = {
    "understanding": "欧米正在理解你的需求",
    "searching": "欧米正在挑选合适的商品",
    "comparing": "欧米正在比对商品差异",
    "checking": "欧米正在核对推荐依据",
    "answering": "欧米正在整理建议",
}

def _stage(stage: str) -> str:
    """面向用户的有限阶段，不泄露 ReAct 内部推理或工具参数。"""
    payload = json.dumps({"version": "chat_event_v1", "stage": stage, "text": _STAGE_TEXT[stage]}, ensure_ascii=False)
    # status 保留给 Web 等存量客户端；stage 是 Android 新的结构化事件。
    return _sse("stage", payload) + _sse("status", payload)


def _recommendation_sections(state):
    from app.services.recommendation_brief import build_recommendation_brief

    primary, alternatives = build_recommendation_brief(state)
    return _slim_products(primary), _slim_products(alternatives)


def _public_decision_results(state, primary: list[dict], alternatives: list[dict]) -> list[dict]:
    """返回卡片真正需要的裁决，不把内部排序分泄露给客户端。

    ``final_score`` / ``component_scores`` 是检索与诊断信号，不是用户应据以
    决策的分数。``recommendation_score`` 是服务端从本轮约束、闭集裁决和
    可追溯资料确定性计算出的展示评分，可安全用于用户比较。
    """
    visible_ids = {
        str(product.get("product_id") or "")
        for product in [*primary, *alternatives]
        if product.get("product_id")
    }
    public: list[dict] = []
    for decision in state.decision_results or []:
        product_id = str(decision.get("product_id") or "")
        if not product_id or product_id not in visible_ids:
            continue
        public.append({
            "product_id": product_id,
            "recommendation_level": decision.get("recommendation_level", "insufficient_evidence"),
            "match_label": decision.get("match_label", ""),
            "evidence_label": decision.get("evidence_label", "信息有限"),
            "why_it_fits": decision.get("why_it_fits", ""),
            "caution": decision.get("caution", ""),
            "risk_factors": list(decision.get("risk_factors") or [])[:2],
            "hard_constraint_status": decision.get("hard_constraint_status", ""),
            "recommendation_score": _safe_dump(decision.get("recommendation_score") or {}),
        })
    return public


def _recommendation_event_payload(state) -> dict:
    primary, alternatives = _recommendation_sections(state)
    focus_pid = getattr(state, "focus_product_id", "") or ""
    dossier = (getattr(state, "product_dossiers", {}) or {}).get(focus_pid) or {}
    dossier_summary = ({
        "product_id": dossier.get("product_id", focus_pid),
        "title": dossier.get("title", ""),
        "evidence_status": dossier.get("evidence_status", "信息有限"),
        "information_gaps": dossier.get("information_gaps", []),
    } if dossier else None)
    # ``visual_result`` is a fact about a user-uploaded image, not a general
    # retrieval hint.  Some focused/internal paths may attach an image URL for
    # product data; never let that implementation detail turn into a false
    # “we recognised your image” notice on a text-only conversation.
    has_user_image = bool(getattr(state, "image_url", None))
    visual_result = getattr(state, "visual_result", None) if has_user_image else None
    return {
        # Public SSE DTO marker.  New clients can feature-detect additions while
        # existing ones keep consuming the stable compatibility fields below.
        "version": "chat_event_v1",
        "primary_products": _safe_dump(primary),
        "alternative_products": _safe_dump(alternatives),
        "decision_results": _safe_dump(_public_decision_results(state, primary, alternatives)),
        "evidence_list": _safe_dump(
            _slim_evidence(state.evidence_list or [], state.primary_product_ids or [], primary + alternatives)
        ),
        "recommendation_brief": _safe_dump(state.recommendation_brief or []),
        "product_resolution": _safe_dump(state.product_resolution or {}),
        "retrieval_scope": state.retrieval_scope or "broad",
        "resolved_product_ids": _safe_dump(state.resolved_product_ids or []),
        "retrieval_groups": _safe_dump(state.retrieval_groups or []),
        # V9 按工具调用/需求组暴露有限的可视化状态；不泄露原始 Chunk、Prompt 或推理。
        "candidate_groups": _safe_dump([
            {"group_id": group.get("group_id", ""), "query": group.get("query", ""),
             "source": group.get("source", ""), "filter_status": (group.get("filter") or {}).get("status", ""),
             "missing_reason": (group.get("filter") or {}).get("missing_group", ""),
             "product_ids": [p.get("product_id", "") for p in (group.get("products") or [])]}
            for group in (getattr(state, "candidate_groups", []) or []) if isinstance(group, dict)
        ]),
        "product_dossier": _safe_dump(dossier_summary),
        # Optional, concise visual status for clients.  It contains recognition
        # facts only, never raw image bytes, prompts, or internal candidates.
        "visual_result": _safe_dump(visual_result or {}),
        "visual_resolution": _safe_dump(
            (getattr(state, "product_resolution", {}) or {}).get("source") == "visual_catalog"
        ),
    }


def _result_with_recommendations(
    state, *, session_id: str, conversation_id: str, answer: str, analysis_alternatives: list | None = None, **extra
) -> dict:
    recommendation = _recommendation_event_payload(state)
    result = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "answer": answer,
        # 旧客户端继续读取 products；新客户端使用主推/备选两个显式分区。
        "products": recommendation["primary_products"] + recommendation["alternative_products"],
        **recommendation,
        "trace_steps": _safe_dump(state.trace_steps or []),
        "harness_report": _safe_dump(state.harness_report or {}),
        # 受控运行时仅暴露安全摘要，方便客户端/评测判断是否发生重复检索；不含
        # 原始 Prompt、工具参数全文或模型内部推理。
        "tool_trace_summary": _safe_dump([
            {
                "tool_call_id": item.get("tool_call_id", ""),
                "name": item.get("name", ""),
                "group_id": item.get("group_id", ""),
                "status": item.get("status", ""),
                "latency_ms": item.get("latency_ms", 0),
            }
            for item in (getattr(state, "tool_ledger", []) or [])
        ]),
        "tool_budget": _safe_dump(getattr(state, "tool_budget", {}) or {}),
    }
    if analysis_alternatives is not None:
        result["analysis_alternatives"] = _safe_dump(analysis_alternatives)
    result.update(extra)
    return result


# ============================================================
# 辅助: 上下文增强
# ============================================================


async def _generate_title(cid: str, user_id: str, conv_svc, first_query: str, first_answer: str):
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
        await conv_svc.aupdate_context_snapshot(cid, {"title": title}, user_id=user_id)
        # 同时更新 conversations 表的 title 字段
        try:
            from app.core.database import get_session_sync
            from app.models.conversation import ConversationModel
            from sqlalchemy import update

            factory = get_session_sync()
            async with factory() as session:
                await session.execute(
                    update(ConversationModel).where(ConversationModel.conversation_id == cid, ConversationModel.user_id == user_id).values(title=title)
                )
                await session.commit()
        except Exception:
            pass


# ============================================================
# 辅助: 写入聚焦商品到 conversation context_snapshot（读取/地址解析已收敛到 ShopActionAgent）
# ============================================================
async def _write_focus_product(conv_svc, conversation_id: str, product, user_id: str):
    """问欧米点击时锁定商品 → context_snapshot"""
    if not conv_svc or not conversation_id:
        return
    try:
        await conv_svc.set_focus_product(conversation_id, product, user_id=user_id)
    except Exception as e:
        logger.warning(f"Failed to write focus_product: {e}")


def _build_focus_analysis(dossier: dict) -> dict:
    review = dossier.get("review_summary") or {}
    highlights: list[str] = []
    if dossier.get("marketing_description"):
        highlights.append("商品说明已核对")
    if dossier.get("official_faq"):
        highlights.append(f"官方问答覆盖 {len(dossier['official_faq'])} 个问题")
    if review.get("avg_rating") is not None:
        highlights.append(f"口碑 {review.get('avg_rating')}/5")
    price_range = dossier.get("price_range") or {}
    return {
        "product_id": dossier.get("product_id"),
        "title": dossier.get("title"),
        "brand": dossier.get("brand"),
        "price": dossier.get("price"),
        "price_range": {
            "min": price_range.get("min", dossier.get("price", 0)),
            "max": price_range.get("max", dossier.get("price", 0)),
        },
        "image_url": f"/api/products/{dossier.get('product_id')}/image",
        "rating": {"avg": review.get("avg_rating"), "count": review.get("count", 0)},
        "highlights": highlights[:3],
        "cautions": list(dossier.get("information_gaps") or [])[:2],
        "suitable_for": f"{dossier.get('sub_category') or dossier.get('category') or '同类'}选购人群",
        "evidence_status": dossier.get("evidence_status", "信息有限"),
    }


def _focused_filter_bucket(message: str) -> str:
    """为单品档案区分“介绍商品”和“验证特定使用条件”。"""
    query = (message or "").lower()
    scenario_words = ("海边", "户外", "暴晒", "下水", "出汗", "敏感肌", "油皮", "干皮", "孕", "儿童", "跑步", "登山")
    # “问欧米/介绍/怎么样”只是对已锁定主体的资料咨询；此时不应凭空扣分。
    # 一旦用户问到具体场景或人群，档案只能给“有条件匹配”——除非后续专门
    # 检索到充分事实，不让被点选这一动作替代真实适配判断。
    return "conditional" if any(word in query for word in scenario_words) else "primary"


def _focused_product_payload(product, dossier: dict, *, filter_bucket: str = "primary") -> dict:
    """把可信商品主数据收敛成单品分析唯一可交付的卡片。

    商品聚焦不是一次泛检索：用户已经点中了唯一的 ``product_id``。仍然要把
    它转换为标准商品卡并交给 Decision/Brief，才能让卡片、指数、标签和正文
    使用同一个事实来源。
    """
    raw_knowledge = product.rag_knowledge
    knowledge = (
        raw_knowledge.model_dump() if hasattr(raw_knowledge, "model_dump") else dict(raw_knowledge or {})
    )
    evidence_types: list[str] = []
    if dossier.get("marketing_description"):
        evidence_types.append("marketing")
    if dossier.get("official_faq"):
        evidence_types.append("faq")
    if (dossier.get("review_summary") or {}).get("count", 0):
        evidence_types.append("review")
    return {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": product.base_price,
        "image_urls": [f"/api/products/{product.product_id}/image"],
        "skus": [sku.model_dump() if hasattr(sku, "model_dump") else dict(sku) for sku in product.skus],
        # 营销长文仅留在服务端档案/证据中。直接放到卡片上不仅阅读负担重，
        # 还会让未经筛选的宣传数字绕开最终回答的受控表达。
        "description": "",
        "rag_knowledge": knowledge,
        "filter_bucket": filter_bucket,
        "card_reason": "你已锁定这件商品，欧米只依据它的商品资料为你核对。",
        "evidence_types": evidence_types,
    }


def _short_product_name(product: dict, limit: int = 32) -> str:
    """去掉重复品牌后的紧凑商品名，避免把营销长标题塞进自然语言。"""
    title = " ".join(str(product.get("title") or "").split())
    brand = str(product.get("brand") or "").strip()
    if brand and title.startswith(brand):
        title = title[len(brand):].lstrip(" -·")
    # 标题在容量/年份后的营销尾巴通常很长；不要截在括号或数字中间。
    for marker in ("（", "("):
        if marker in title:
            title = title.split(marker, 1)[0].rstrip()
    return title[:limit].rstrip("，、。；; ") or brand or "这件商品"


def _focused_answer(dossier: dict, product: dict, message: str) -> str:
    """生成单品档案的可追溯答复，不让展示层再编造营销事实。

    聚焦页的原 LLM 摘要曾把长营销文案扩写成不可验证的性能数字，也会绕过
    主回答 Guard。这里刻意只使用标题/规格、价格区间、FAQ 与评价汇总这些
    已结构化的字段；文本仍按块 SSE 发送，用户可持续看到输出。
    """
    name = _short_product_name(product)
    brand = str(product.get("brand") or "").strip()
    price_range = dossier.get("price_range") or {}
    low = price_range.get("min", product.get("price", 0))
    high = price_range.get("max", low)
    price_text = f"¥{low:g}" if low == high else f"¥{low:g}–{high:g}"
    sku_values: list[str] = []
    for sku in dossier.get("skus") or []:
        values = (sku.get("properties") or {}).values() if isinstance(sku, dict) else []
        for value in values:
            value = str(value).strip()
            if value and value not in sku_values:
                sku_values.append(value)
    specs = "、".join(sku_values[:5])
    review = dossier.get("review_summary") or {}
    review_count = int(review.get("count") or 0)
    avg_rating = review.get("avg_rating")
    faq_count = len(dossier.get("official_faq") or [])
    query = (message or "").lower()
    outdoor = any(word in query for word in ("海边", "户外", "暴晒", "下水", "出汗", "旅行", "旅游"))

    sentences = [
        f"你看的这款{brand}{name}，当前可用规格信息为{specs or '以详情页规格为准'}，价格{price_text}。",
    ]
    if outdoor and "SPF" in specs.upper():
        sentences.append("去海边时可以重点看它标注的防晒规格；长时间日晒、出汗或下水后仍应按产品说明及时补涂。")
    elif outdoor:
        sentences.append("用于户外前，建议先确认详情页的防护等级和使用说明；长时间日晒、出汗或下水后要及时补涂或补充防护。")
    if faq_count:
        sentences.append(f"现有资料包含{faq_count}条官方问答，可进一步核对使用方式和规格差异。")
    if review_count and avg_rating is not None:
        sentences.append(f"用户评价目前有{review_count}条，平均{float(avg_rating):g}/5；样本不多，建议把它当作参考，再结合自己的肤质和使用场景判断。")
    elif review_count:
        sentences.append(f"目前有{review_count}条用户评价，建议下单前再查看详情页中的具体反馈。")
    else:
        sentences.append("目前可用的用户评价较少，购买前建议重点确认适配性和售后规则。")
    return "".join(sentences)


async def _stream_plain_text(text: str) -> AsyncGenerator[str, None]:
    """用自然语义小段推送确定性回答，避免 Markdown 字符逐 token 闪现。"""
    for offset in range(0, len(text), _STREAM_CHUNK_SIZE):
        yield _sse("token", json.dumps({"text": text[offset:offset + _STREAM_CHUNK_SIZE]}, ensure_ascii=False))
        await asyncio.sleep(_STREAM_CHUNK_DELAY_SECONDS)


async def _collect_answer(request: Request, upstream, *, fallback: str = "") -> str | None:
    chunks = []
    try:
        async for token in upstream:
            if await request.is_disconnected():
                return None
            chunks.append(token)
    except Exception:
        logger.warning("Answer provider failed before delivery", exc_info=True)
        return fallback
    return "".join(chunks).strip() or fallback


def _comparison_answer(comparison: dict) -> str:
    """对比卡的文字结论只复述已经下发的横向事实，避免另起一套 LLM 事实。"""
    items = [comparison.get("target") or [], *(comparison.get("alternatives") or [])]
    descriptions: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _short_product_name(item, limit=18)
        price = item.get("price")
        attributes = item.get("attributes") or {}
        facts = [str(value) for key, value in attributes.items() if key != "价格" and value and value != "以商品详情为准"]
        suffix = f"，{ '、'.join(facts[:2]) }" if facts else ""
        descriptions.append(f"{item.get('brand', '')}{title}约¥{price:g}{suffix}")
    verdict = (comparison.get("verdict") or {}).get("text") or "建议按价格、核心特点和适用场景选择。"
    return "。".join(descriptions[:4]) + ("。" if descriptions else "") + str(verdict)


def _focused_comparison_payload(state, target):
    """Legacy read-only adapter retained for old clients/tests.

    Production comparison is built by ``same_category_comparison``.  This helper
    deliberately has no model call and only projects already-retrieved, strictly
    same-subcategory items into the former table contract.
    """
    target_id = str(getattr(target, "product_id", ""))
    category = str(getattr(target, "category", ""))
    sub_category = str(getattr(target, "sub_category", ""))
    candidates = [
        item for item in (state.retrieved_products or [])
        if str(item.get("product_id", "")) != target_id
        and str(item.get("category", "")) == category
        and (not sub_category or str(item.get("sub_category", "")) == sub_category)
    ][:3]
    alternatives = [{
        "product_id": item.get("product_id", ""), "title": item.get("title", ""), "brand": item.get("brand", ""),
        "price": item.get("price", item.get("base_price", 0)), "category": item.get("category", ""),
        "sub_category": item.get("sub_category", ""),
    } for item in candidates]
    dimensions = ["商品", "价格", "核心特点", "适合场景"]
    target_name = f"{getattr(target, 'brand', '')} {getattr(target, 'title', '')}".strip()
    target_values = [target_name, f"¥{getattr(target, 'base_price', 0):g}", f"{sub_category or category}基础款", "日常使用"]
    alternative_values = [[
        f"{item['brand']} {item['title']}".strip(), f"¥{float(item['price'] or 0):g}",
        f"{item['sub_category'] or item['category']}基础款", "日常护肤",
    ] for item in alternatives]
    target_card = {"product_id": target_id, "title": getattr(target, "title", ""), "brand": getattr(target, "brand", ""),
                   "price": getattr(target, "base_price", 0), "category": category, "sub_category": sub_category}
    return alternatives, {"dimensions": dimensions, "target_values": target_values, "alternative_values": alternative_values}, [target_card, *alternatives]


# ============================================================
# 路由
# ============================================================


class ConfirmShoppingActionRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=2000)


@router.post("/confirm-shop-action")
async def confirm_shop_action(req: ConfirmShoppingActionRequest, actor: Actor = Depends(resolve_public_actor)):
    from app.services.shop_action_confirmation import confirm_order_action

    return await confirm_order_action(require_user(actor).user_id, req.confirmation)


@router.post("/stream")
async def recommend_stream(req: StreamRequest, raw_request: Request, actor: Actor = Depends(resolve_public_actor)):

    async def gen() -> AsyncGenerator[str, None]:
        sid = req.session_id or str(_uuid.uuid4())[:8]
        uid = actor.user_id
        # 游客只拥有本次请求的临时身份；不能读写会话、偏好或购物上下文。
        can_persist = actor.is_authenticated
        cid = req.conversation_id if can_persist else ""
        msg = req.message or ""
        logger.info(
            "chat stream start request=%s mode=%s actor=%s image=%s deep=%s",
            sid, req.mode, actor.kind, bool(req.image_url), bool(req.deep_think),
        )
        yield _stage("understanding")

        # ---- 初始化 conv_svc ----
        conv_svc = None
        try:
            from app.services.conversation_service import get_conversation_service

            conv_svc = get_conversation_service()
        except Exception as e:
            logger.warning(f"conv_svc init failed: {e}")

        # P0-3: 会话创建/用户消息落库上移到支付与购物块之前——
        # 支付/报告/购物等早退轮次同样入历史，且后续 pending 快照有真实 cid 可写
        if can_persist and conv_svc:
            try:
                conv_result = await conv_svc.aget_or_create(
                    user_id=uid,
                    session_id=sid,
                    conversation_id=cid,
                )
                cid = conv_result["conversation_id"]
            except Exception:
                pass
            if cid:
                try:
                    await conv_svc.aappend_user_message(
                        conversation_id=cid,
                        user_id=uid,
                        session_id=sid,
                        content=req.message,
                        image_url=req.image_url or "",
                    )
                except Exception:
                    pass

        from app.framework.tools import ToolContext
        from app.services.chat_shopping_router import run_shopping_turn

        shopping = await run_shopping_turn(
            ToolContext(user_id=uid, session_id=sid, conversation_id=cid, args_raw=msg), conv_svc,
            authenticated=can_persist,
            payment_available=req.cart_payment and settings.report_payment_mode != "disabled",
            catalogue_only=bool(req.image_url) or req.mode != "normal_recommend",
        )
        shopping_prefix = shopping.message if shopping and shopping.data.get("workflow_after") else ""
        if shopping and shopping.data.get("cart_changed"):
            yield _sse("cart_changed", "{}")
        if shopping is not None and not shopping_prefix:
            data = shopping.data
            payload = {
                "answer": shopping.message, "products": [], "decision_results": [],
                "shop_action": True, "conversation_id": cid, "session_id": sid,
                "actions": shopping.actions, "shop_card": data.get("shop_card"),
            }
            if data.get("requires_login"):
                payload["requires_login"] = True
            if can_persist and conv_svc and cid and shopping.message:
                try:
                    await conv_svc.aappend_assistant_message(
                        conversation_id=cid, user_id=uid, session_id=sid, content=shopping.message,
                        metadata={"shop_card": data.get("shop_card"), "actions": shopping.actions},
                    )
                except Exception:
                    logger.debug("Could not persist shopping reply")
            async for event in _stream_plain_text(shopping.message):
                yield event
            yield _sse("result", json.dumps(payload, ensure_ascii=False, default=str))
            yield _sse("done", json.dumps({"finish_reason": "login_required" if data.get("requires_login") else "stop"}))
            return

        from langgraph.errors import GraphRecursionError
        from app.core.config import ENABLE_AGENT_LOOP

        if ENABLE_AGENT_LOOP and req.deep_think and req.mode == "normal_recommend":
            from app.framework.blackboard import Blackboard, reset_current_board, set_current_board
            from app.schemas.workflow import WorkflowState as _WS

            # 门控已要求 req.deep_think，故档位固定为 max（Plan-Execute）。
            _loop_state = _WS(
                session_id=sid, user_id=uid, conversation_id=cid, user_query=msg,
                image_url=req.image_url, mode="max", allow_tool_writes=False,
            )
            # 深度模式只在 Loop 前做 Router，不做前置泛检索。检索是受控工具，
            # 必须由 ReAct 在拿到 Router Plan 后按需调用；此前“预检索 + Loop 再搜”
            # 会为同一个目标重复 embedding、rerank 与 LLM Filter。
            try:
                from app.workflow.graph import _node_router, _node_visual

                yield _stage("understanding")
                _loop_state = await _node_visual(_loop_state)
                _loop_state = await _node_router(_loop_state)
            except Exception as exc:  # Loop 仍可在 Router 降级时自主理解请求
                logger.warning("deep router preflight degraded: %s", exc)
            # 请求级黑板：工具的 ToolResult.artifacts 经 build_tool_ctx 落到这块板上。
            _bb_token = set_current_board(Blackboard())
            _loop_ok = False
            _loop_actions: list = []  # 工具产出的交互动作（如 sku_option 规格选择按钮）
            try:
                # ReAct 图（standard/max 双档同构，移植 amap chat_agent 的编排结构）。
                # status 事件从 trace_steps 增量派生 —— 图节点返回 state patch，没有向
                # SSE 直推事件的通道，而 trace 本就逐步记录了"做了什么"，拿它当事件源
                # 就不必新建一层事件总线。
                from app.workflow.react import get_react_workflow, run_config
                from app.workflow.react.common import status_text as _status_text

                # standard 档（纯 ReAct，不产 todo 计划）目前只由单测与 OmniAgent 薄壳
                # 覆盖：默认非深度请求仍走下方 pipeline，把它也换成图是另一个量级的变更。
                _mode = _loop_state.mode
                _seen = 0
                async for _chunk in get_react_workflow(_mode).astream(_loop_state, config=run_config(_mode)):
                    for _node_out in _chunk.values():
                        if not isinstance(_node_out, dict):
                            continue
                        _loop_state = _WS(**_node_out)
                        for _tr in (_loop_state.trace_steps or [])[_seen:]:
                            _txt = _status_text(_tr.get("action", ""))
                            if _txt:
                                action = _tr.get("action", "")
                                stage = (
                                    "checking"
                                    if any(k in action for k in ("check", "verify", "finalize"))
                                    else "comparing"
                                    if any(k in action for k in ("search", "retrieve", "tool"))
                                    else "understanding"
                                )
                                yield _stage(stage)
                        _seen = len(_loop_state.trace_steps or [])
                # 工具产出的交互动作（sku_option 规格选择等）必须透传，否则多规格商品
                # 加购时前端的规格选择按钮会消失，用户只能纯对话选。
                _loop_actions = list(_loop_state.tool_actions or [])
                _loop_ok = True
            except GraphRecursionError:
                # 递归上限先于 check_iteration 触发 == 预算守卫失效，是编程错误而非
                # LLM 抖动。单独记 ERROR + 堆栈，否则会和瞬时故障一起被 warning 淹没，
                # 生产上表现为"深度思考静默退化成 pipeline"，极难察觉。
                logger.error(
                    "react graph hit recursion limit — budget guard is not the binding constraint, check run_config()",
                    exc_info=True,
                )
            except Exception as e:  # noqa: BLE001 — LLM 异常降级到既有 workflow
                logger.warning(f"agent loop failed, falling back to workflow: {e}")
            finally:
                reset_current_board(_bb_token)

            if _loop_ok:
                # ReAct content 属于推理/工具协议，不能作为终稿。卡片锁定后由同一
                # AnswerContext 生成真实流式回答，深度模式与普通模式不再有两套上下文。
                from app.workflow.graph import _node_decision, _node_reranker, get_response_agent, get_response_guard

                try:
                    # 工具运行时已完成 V9 rerank/filter 的请求会跳过重复精排；这里仅在
                    # Loop 收敛后统一补一次决策，保证卡片、简报与终稿共享同一结果集。
                    _loop_state = await _node_reranker(_loop_state)
                    _loop_state = await _node_decision(_loop_state)
                    _recommendation_sections(_loop_state)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"loop answer generation failed: {e}")
                yield _stage("checking")
                yield _sse(
                    "recommendations",
                    json.dumps(_recommendation_event_payload(_loop_state), ensure_ascii=False, default=str),
                )
                yield _stage("answering")
                from app.verification.response_delivery import finalize_response

                candidate = await _collect_answer(raw_request, get_response_agent().generate_stream(_loop_state))
                if candidate is None:
                    return
                from app.services.recommendation_brief import build_recommendation_brief

                primary, _ = build_recommendation_brief(_loop_state)
                _answer = finalize_response(_loop_state, candidate, get_response_guard(), cards=primary)
                if shopping_prefix:
                    _answer = shopping_prefix + "\n\n" + _answer
                _payload = _result_with_recommendations(
                    _loop_state,
                    session_id=sid,
                    conversation_id=cid,
                    answer=_answer,
                    skill_executions=_safe_dump(_loop_state.skill_executions or []),
                    agent_loop=True,
                    deep_think=req.deep_think,
                )
                if _loop_actions:
                    _payload["actions"] = _safe_dump(_loop_actions)
                # 持久化：助手消息 + last_products 快照（供下一轮指代）
                if can_persist and conv_svc and cid:
                    try:
                        await conv_svc.aappend_assistant_message(
                            conversation_id=cid, user_id=uid, session_id=sid, content=_answer
                        )
                        await conv_svc.apersist_answer_context(
                            conversation_id=cid, user_id=uid, state=_loop_state, answer=_answer,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                async for event in _stream_plain_text(_answer):
                    yield event
                yield _sse("result", json.dumps(_payload, ensure_ascii=False, default=str))
                yield _sse("done", json.dumps({"finish_reason": "stop"}))
                return
            # Loop 失败 → 继续落入下方既有链路（购物门控 / workflow）

        # ================================================================
        # 以下是原有的推荐/聚焦分析流程 (保持不变)
        # ================================================================
        import time as _time

        _t_total_start = _time.perf_counter()

        focus_pid = (req.target_product_id or "").strip() if req.mode in {"product_focused_analysis", "same_category_comparison"} else ""
        is_focused = bool(focus_pid)

        # P2-2: 检索/生成前发中间态（前端未订阅的事件类型会静默忽略）
        yield _stage("searching")

        # P0: conversation —— 已上移至购物块之前（P0-3），此处不再重复创建/落库

        # P2 + P4: FollowUpEngine + Profile 并行加载
        _t0 = _time.perf_counter()
        route_query = (shopping.data.get("workflow_query") if shopping_prefix else "") or req.message
        enriched_query = route_query
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
                    if can_persist and cid:
                        _snap = await conv_svc.aget_context_projection(cid, user_id=uid)
                except Exception:
                    _snap = None
                fu = engine.detect(conversation_id=cid, session_id=sid, current_query=req.message, snapshot=_snap)
                if fu.get("is_follow_up") and fu.get("context_prompt"):
                    enriched_query = f"{route_query}\n\n{fu['context_prompt']}"
                if fu.get("updated_constraints"):
                    followup_constraints = fu["updated_constraints"]
                return fu
            except Exception:
                return {}

        async def _run_profile():
            try:
                if can_persist:
                    from app.services.user_profile_service import get_user_profile_service

                    return await get_user_profile_service().inject_profile_hints(
                        uid,
                        query=req.message,
                        enriched_query=req.message,
                        context_prompt="",
                    )
            except Exception:
                pass
            return {"enriched_query": req.message, "context_prompt": "", "avoid_tags": []}

        import asyncio as _asyncio

        follow_up, hints_result = await _asyncio.gather(_run_followup(), _run_profile())
        # 合并：FollowUp context_prompt + Profile context_prompt
        context_prompt = "\n".join(filter(None, (
            follow_up.get("context_prompt", ""), hints_result["context_prompt"], shopping_prefix,
        )))
        # 如果 FollowUp 改写了 query，保留改写版本；否则用 profile 增强版
        if enriched_query == req.message:
            enriched_query = hints_result["enriched_query"]
        logger.info(f"⏱ followup+profile: {(_time.perf_counter() - _t0) * 1000:.0f}ms (parallel)")

        # 文本指定商品、问欧米之外的图片识别，只有解析器确认“唯一精确商品”才
        # 升级为单品档案；系列、歧义和泛品类仍走原推荐链路，避免过度锁定。
        # 图片身份解析只允许在工作流最前置的 visual 节点执行一次；此处
        # 仅保留纯文本的便捷聚焦判断，避免 SSE 层与工作流重复调用视觉模型。
        if not is_focused and not req.image_url:
            try:
                from app.services.product_entity_resolver import ProductEntityResolver

                resolution = await ProductEntityResolver().resolve(enriched_query)
                resolved_ids = list(resolution.payload.get("resolved_product_ids") or [])
                is_exact = resolution.payload.get("match_type") == "exact_product" and len(resolved_ids) == 1
                detail_words = ("介绍", "优缺点", "参数", "配置", "规格", "评价", "口碑", "怎么样", "适合", "值得")
                if is_exact and (bool(req.image_url) or any(word in req.message for word in detail_words)):
                    focus_pid = resolved_ids[0]
                    is_focused = True
            except Exception as exc:  # noqa: BLE001 -- 身份层/视觉层不可用不能阻断普通推荐
                logger.debug("pre-ReAct product focus resolution skipped: %s", exc)

        # P4: 对话提取检查 — 后台执行，不阻塞用户看到回复
        try:
            if can_persist:
                from app.services.user_profile_service import get_user_profile_service

                _svc = get_user_profile_service()
                if _svc.has_long_term_signal(req.message):
                    asyncio.create_task(_svc.parse_and_merge(uid, req.message))
        except Exception:
            pass

        # 点选商品属于可信 ID 聚焦：先建立唯一单品档案，再走与普通推荐一致的
        # Decision/Brief/SSE 卡片协议。单品事实交付不再另起自由生成链路。
        if is_focused:
            import re

            from app.agents.decision_agent import DecisionAgent
            from app.providers.tools.shopping import build_product_dossier
            from app.repositories.product_repo import get_product_repo
            from app.schemas.workflow import WorkflowState
            from app.services.recommendation_brief import build_recommendation_brief

            target_pid = focus_pid
            target = get_product_repo().get_by_id(target_pid)
            comparison_requested = req.mode == "same_category_comparison" or (
                bool(req.allow_same_category_comparison)
                and bool(re.search(r"对比|横向|同类|替代|更好选择", req.message or ""))
            )

            if not target:
                answer = "抱歉，我没找到这件商品的信息。你可以重新从商品页点一下，我马上帮你核对～"
                yield _stage("answering")
                yield _sse("token", json.dumps({"text": answer}, ensure_ascii=False))
                yield _sse("result", json.dumps({
                    "session_id": sid, "conversation_id": cid, "answer": answer,
                    "products": [], "focus_analysis": None, "comparison": None,
                }, ensure_ascii=False))
                yield _sse("done", json.dumps({"finish_reason": "stop"}))
                return

            await _write_focus_product(conv_svc, cid, target, uid)
            target_dossier = build_product_dossier(target, "overview")
            repo = get_product_repo()
            focus_state = WorkflowState(
                session_id=sid,
                user_id=uid,
                conversation_id=cid,
                user_query=req.message,
                intent="product_focused_analysis",
                retrieved_products=[_focused_product_payload(
                    target, target_dossier, filter_bucket=_focused_filter_bucket(req.message),
                )],
                retrieval_scope="exact_product",
                resolved_product_ids=[target.product_id],
                focus_product_id=target.product_id,
                product_dossiers={target.product_id: target_dossier},
                product_resolution={
                    "match_type": "exact_product",
                    "resolved_product_ids": [target.product_id],
                    "source": "target_product_id",
                },
                # 使简报、卡片和该模式的 Decision 共享 v9 展示契约；这里没有
                # 泛检索分数，指数只反映锁定商品对本次问题、预算与资料的适配。
                structured_retrieval_report={"version": "v9", "source": "product_dossier"},
                sufficiency_report={"sufficient": target_dossier.get("evidence_status") == "证据充分"},
            )
            await DecisionAgent().execute(focus_state)
            primary_products, alternative_products = build_recommendation_brief(focus_state)
            focus_decision = (focus_state.decision_results or [{}])[0]

            # 和普通推荐使用完全一致的交付顺序：先锁定可信商品卡，随后再给
            # 单品档案或同类横向表，最后才开始自然语言 token 流。这样 Web 与
            # Android 可以共用一套状态机，不需要根据“问欧米”反转渲染顺序。
            yield _sse(
                "recommendations",
                json.dumps(_recommendation_event_payload(focus_state), ensure_ascii=False, default=str),
            )

            if comparison_requested:
                yield _stage("comparing")
                # 横向对比是独立工作流，而不是普通商品卡的附属排序：先在严格
                # 同子类中去重，并覆盖低价/相近/升级价格带；再由 LLM 只在已核
                # 对的事实闭集内完成条件化裁决。这样既不会被“评价高”绑架，也
                # 不会把模型幻觉写进卡片。
                from app.services.same_category_comparison import build_same_category_comparison

                comparison, comparison_dossiers = await build_same_category_comparison(
                    repo, target, req.message,
                )
                comparison["version"] = "chat_event_v1"
                focus_state.product_dossiers.update(comparison_dossiers)
                yield _stage("checking")
                yield _sse("comparison", json.dumps(comparison, ensure_ascii=False, default=str))
            else:
                focus_analysis = _build_focus_analysis(target_dossier)
                focus_analysis["version"] = "chat_event_v1"
                focus_analysis["recommendation_score"] = focus_decision.get("recommendation_score") or {}
                focus_analysis["match_label"] = focus_decision.get("match_label", "")
                focus_analysis["why_it_fits"] = focus_decision.get("why_it_fits", "")
                focus_analysis["caution"] = focus_decision.get("caution", "")
                yield _stage("checking")
                yield _sse("focus_analysis", json.dumps(focus_analysis, ensure_ascii=False, default=str))

            yield _stage("answering")
            from app.verification.response_delivery import finalize_response
            from app.workflow.graph import get_response_agent, get_response_guard

            if comparison_requested:
                from app.model_gateway.gateway import get_model_gateway
                from app.prompts.api_prompts import COMPARISON_RESPONSE_SYSTEM, build_comparison_response_prompt

                cards = [comparison["target"], *comparison["alternatives"]]
                upstream = get_model_gateway().chat_stream(
                    "chat_generation", build_comparison_response_prompt(comparison, req.message),
                    COMPARISON_RESPONSE_SYSTEM,
                )
            else:
                cards = None
                upstream = get_response_agent().generate_stream(focus_state)

            candidate = await _collect_answer(raw_request, upstream)
            if candidate is None:
                return
            answer = finalize_response(focus_state, candidate, get_response_guard(), cards=cards)
            if shopping_prefix:
                answer = shopping_prefix + "\n\n" + answer
            result = _result_with_recommendations(
                focus_state, session_id=sid, conversation_id=cid, answer=answer,
            )
            if comparison_requested:
                result["comparison"] = comparison
            else:
                result["focus_analysis"] = focus_analysis
            if can_persist and conv_svc and cid:
                try:
                    await conv_svc.aappend_assistant_message(
                        conversation_id=cid, user_id=uid, session_id=sid, content=answer,
                        product_refs=[p["product_id"] for p in result["products"] if p.get("product_id")],
                    )
                    focus_record = {
                        "product_id": target.product_id,
                        "title": target.title,
                        "brand": target.brand,
                        "category": target.category,
                        "sub_category": target.sub_category,
                        "price": target.base_price,
                        "locked_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await conv_svc.aupdate_context_snapshot(cid, {
                        "focus_product": focus_record,
                        "last_products": [
                            {key: product.get(key) for key in ("product_id", "title", "brand", "price")}
                            for product in result["products"] if product.get("product_id")
                        ] or [focus_record],
                        "last_products_at": focus_record["locked_at"],
                        "pending_question": None,
                    }, user_id=uid)
                except Exception:
                    pass
            async for event in _stream_plain_text(answer):
                yield event

            yield _sse("result", json.dumps(result, ensure_ascii=False, default=str))
            yield _sse("done", json.dumps({"finish_reason": "stop"}))

            return

        try:
            target_analysis = None
            alternatives = []
            comparison = None
            cross_category = []

            # 构建 prefill (FollowUpEngine 检测到的追问约束)
            _t_wf = _time.perf_counter()
            profile_avoid = hints_result.get("avoid_tags") or []
            prefill = _build_constraint_prefill(followup_constraints, profile_avoid)
            # 真流式：no_response 图只跑到 decision，回答由下方 generate_stream 边生成边推
            state = await run_workflow(
                user_query=enriched_query,
                image_url=req.image_url,
                session_id=sid,
                user_id=uid,
                conversation_id=cid,
                enable_checkpoint=False,
                prefill_state=prefill,
                context_prompt=context_prompt,
                no_response=True,
                fast_mode=req.fast_mode,
                mode=req.exec_mode,
            )
            # profile / FollowUp 扩写只服务 Router 与 retrieval。图结束后将
            # 用户原话恢复为最终回答上下文的当前请求，避免泄露内部拼接语料。
            state.user_query = req.message
            state.user_query_original = None
            logger.info(
                f"⏱ workflow: {(_time.perf_counter() - _t_wf) * 1000:.0f}ms (total: {(_time.perf_counter() - _t_total_start) * 1000:.0f}ms)"
            )
            if hasattr(state, "timing") and state.timing:
                logger.info(f"⏱ breakdown: {json.dumps(state.timing, ensure_ascii=False, default=str)}")

            # Visual recognition is a user-facing fact, not merely a retrieval
            # hint. It arrives before cards/prose so clients can explain what
            # was actually recognised instead of silently recommending.
            if req.image_url:
                visual_payload = {
                    "version": "chat_event_v1",
                    "visual_result": _safe_dump(getattr(state, "visual_result", None) or {}),
                    "product_resolution": _safe_dump(getattr(state, "product_resolution", {}) or {}),
                }
                yield _sse("visual_result", json.dumps(visual_payload, ensure_ascii=False, default=str))

            # 商品卡可以先送达，正文在 Guard 完成后统一发送。
            from app.services.recommendation_brief import build_recommendation_brief

            primary, _ = build_recommendation_brief(state)
            yield _stage("checking")
            yield _sse(
                "recommendations", json.dumps(_recommendation_event_payload(state), ensure_ascii=False, default=str)
            )
            yield _stage("answering")
            _t_resp = _time.perf_counter()
            from app.verification.response_delivery import finalize_response
            from app.workflow.graph import get_response_agent, get_response_guard

            candidate = state.answer or await _collect_answer(raw_request, get_response_agent().generate_stream(state))
            if candidate is None:
                return
            answer = finalize_response(state, candidate, get_response_guard(), cards=primary)
            if shopping_prefix:
                answer = shopping_prefix + "\n\n" + answer
            state.timing["response_ms"] = round((_time.perf_counter() - _t_resp) * 1000)
            result = _result_with_recommendations(
                state,
                session_id=sid,
                conversation_id=cid,
                answer=answer,
                analysis_alternatives=alternatives,
                used_memories=_safe_dump(state.used_memories or []) if can_persist else [],
                blocked_memories=_safe_dump(state.blocked_memories or []) if can_persist else [],
                memory_trace=_safe_dump(state.memory_trace or {}) if can_persist else {},
                needs_clarification=state.needs_clarification,
                clarification_question=state.clarification_question,
                clarification_options=_safe_dump(state.clarification_options or []),
                timing=_safe_dump(state.timing or {}),
                target_product_analysis=target_analysis,
                comparison_table=comparison,
                cross_category=cross_category,
            )
            if can_persist and conv_svc and cid:
                await conv_svc.aappend_assistant_message(
                    conversation_id=cid, user_id=uid, session_id=sid, content=answer,
                    product_refs=[p["product_id"] for p in result["products"] if p.get("product_id")],
                )
                await conv_svc.apersist_answer_context(conversation_id=cid, user_id=uid, state=state, answer=answer)
                if not (await conv_svc.get_context_snapshot(cid, user_id=uid)).get("title"):
                    task = asyncio.create_task(_generate_title(cid, uid, conv_svc, req.message, answer[:200]))
                    _BG_TASKS.add(task)
                    task.add_done_callback(_BG_TASKS.discard)
            async for event in _stream_plain_text(answer):
                yield event

            yield _sse("result", json.dumps(result, ensure_ascii=False, default=str))
            yield _sse("done", json.dumps({"finish_reason": "stop"}))

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


def _cited_pids_from_answer(answer: str, products: list) -> list:
    """从终稿文本反推它实际引用了哪些商品，按在回答中出现的先后排序。

    为什么 ReAct 路径需要这一步：``ResponseAgent._context_products`` 设置
    ``answer_cited_pids`` 的前提是"LLM 只看到 retrieved_products 的前 5 个"，
    这在 pipeline 路径成立（reranker+decision 排过序，前 5 即最优）。但 ReAct 路径下
    ``retrieved_products`` 是多次 shopping.search 的**累积**（新结果前插），而 LLM 通过
    context_prompt 的完整工具交互记录看到全部商品 —— 它完全可能推荐第 8 个。
    此时前 5 当引用集就会错位，出现"用户问面霜、首卡是防晒乳"。

    匹配口径与 ``ResponseAgent._answer_cites_products`` 保持一致（品牌名，或标题
    首/尾 6 字，或标题里长度 >= 3 的词），避免两处判定标准打架。
    """
    if not answer or not products:
        return []
    hits: list[tuple[int, str]] = []
    for prod in products:
        pid = prod.get("product_id", "")
        if not pid:
            continue
        title, brand = prod.get("title", ""), prod.get("brand", "")
        candidates = [t for t in (brand, title[:6], title[-6:]) if t and len(t) >= 2]
        candidates += [w for w in title.split() if len(w) >= 3]
        positions = [answer.find(t) for t in candidates]
        positions = [i for i in positions if i >= 0]
        if positions:
            hits.append((min(positions), pid))
    hits.sort(key=lambda x: x[0])
    seen: set[str] = set()
    ordered: list[str] = []
    for _, pid in hits:
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


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
_CARD_KEEP = frozenset(
    {
        "product_id",
        "title",
        "brand",
        "category",
        "sub_category",
        "price",
        "image_urls",
        "skus",
        "description",
        "score",
        "evidence_ids",
        "variant_count",
        "variant_product_ids",
        "beyond_answer",
        "reranker_score",
        "relevance_score",
        "avg_rating",
        "review_count",
        # LLM Filter 已校验的用户可见卡片文案；不能在出口白名单被静默丢弃。
        "filter_bucket",
        "card_reason",
        "evidence_types",
        # 多目标推荐的归属供客户端按“零食/饮品”等用户目标分区展示；它不是
        # 推理过程，也不含工具参数。
        "group_role",
    }
)
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
        # 旧检索缓存、历史会话和少数工具可能未附 image_urls。product_id 对应的图片
        # API 是稳定公开契约，出口统一兜底，避免任何一路漏字段就产生无图卡片。
        if not q.get("image_urls") and q.get("product_id"):
            q["image_urls"] = [f"/api/products/{q['product_id']}/image"]
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
