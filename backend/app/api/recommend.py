import uuid
import time
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.repositories.product_repo import get_product_repo
from app.retrieval.text_retriever import TextRetriever
from app.decision.scoring import DecisionScoring
from app.agents.visual_agent import VisualAgent
from app.core.identity import Actor, resolve_public_actor

router = APIRouter()

_product_repo = get_product_repo()
_retriever = TextRetriever(_product_repo)
_scorer = DecisionScoring()
_visual_agent = VisualAgent()


class RecommendRequest(BaseModel):
    user_query: str
    image_url: Optional[str] = None
    demo_mode: bool = False
    session_id: str = ""
    user_id: str = ""  # V2: 关联长期偏好记忆
    conversation_id: str = ""  # P0: 可恢复聊天线程ID


class RecommendResponse(BaseModel):
    session_id: str
    conversation_id: str = ""  # P0: 返回当前对话ID
    answer: str
    products: list[dict]
    evidence_list: list[dict]
    decision_results: list[dict]
    trace_steps: list[dict]
    visual_result: dict | None
    skill_executions: list
    harness_report: dict
    fallback_status: dict
    retrieval_plan: dict | None = None
    sufficiency_report: dict | None = None
    constraints: dict | None = None
    used_memories: list[dict] = []  # P0: memory_trace 空壳
    blocked_memories: list[dict] = []  # P0: memory_trace 空壳
    memory_trace: dict = {}  # P0: memory_trace 空壳
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_options: list[dict] = []
    timing: dict = {}


@router.post("/api/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest, actor: Actor = Depends(resolve_public_actor)):
    if isinstance(actor, Actor):
        req.user_id = actor.user_id
    session_id = req.session_id or str(uuid.uuid4())[:8]
    trace_steps: list[dict] = []
    visual_result = None

    # ---- Image parse (if provided) ----
    visual_result: dict | None = None
    if req.image_url:
        t0 = time.perf_counter()
        raw = await _visual_agent.parse(req.image_url, req.user_query)
        # 归一化为 dict（缓存命中返回 dict，未命中返回 VisualResult）
        visual_result = raw if isinstance(raw, dict) else raw.model_dump()
        elapsed = round((time.perf_counter() - t0) * 1000)
        trace_steps.append({
            "step_id": "T001",
            "agent_name": "Visual Agent",
            "action": "visual_parse",
            "input_summary": req.image_url,
            "output_summary": (
                f"product={visual_result.get('product_name', '')}, "
                f"brand={visual_result.get('brand', '')}, "
                f"confidence={visual_result.get('confidence', 0)}"
            ),
            "latency_ms": elapsed,
            "status": "success" if visual_result.get("confidence", 0) > 0 else "fallback",
        })
    else:
        trace_steps.append({
            "step_id": "T001",
            "agent_name": "Visual Agent",
            "action": "skipped",
            "input_summary": "no image",
            "output_summary": "no image provided",
            "latency_ms": 0,
            "status": "skipped",
        })

    # ---- Constraint parsing ----
    constraints = _parse_constraints(req.user_query)

    # ---- Load long-term profile ----
    from app.services.user_profile_service import get_user_profile_service
    hints_result = await get_user_profile_service().inject_profile_hints(
        req.user_id, req.user_query, "",
    )
    search_query = hints_result["enriched_query"]
    avoid_tags = hints_result["avoid_tags"]

    # ---- Retrieve ----
    if visual_result and visual_result.get("product_name"):
        search_query = f"{search_query} {visual_result['product_name']} {visual_result.get('brand') or ''}"

    retrieved = await _retriever.search(
        query=search_query,
        top_k=10,
        category=constraints.get("category"),
        sub_category=constraints.get("sub_category"),
        price_max=constraints.get("budget_max"),
        price_min=constraints.get("budget_min"),
    )

    products = []
    decision_results = []
    evidence_list = []

    for item in retrieved:
        product = _product_repo.get_by_id(item["product_id"])
        if product is None:
            continue

        result = _scorer.score(
            product=product,
            query=search_query,
            keyword_score=item.get("score", 0.0),
            budget_max=constraints.get("budget_max"),
            scenario=constraints.get("scenario"),
            visual_result=visual_result,
        )

        products.append(item)
        decision_results.append(result.model_dump())

        for eid in item.get("evidence_ids", []):
            evidence_list.append({
                "evidence_id": eid,
                "source_type": eid.split("-")[0].replace("POL", "policy").replace("R", "review").replace("E", "marketing"),
                "source_id": item["product_id"],
                "product_id": item["product_id"],
                "content": f"Evidence for {item['product_id']}",
                "modality": "text",
                "confidence": min(1.0, item.get("score", 0.0) / 10.0),
            })

    # Add visual evidence
    if visual_result and visual_result.get("evidence_list"):
        for ve in visual_result["evidence_list"]:
            evidence_list.append({
                "evidence_id": ve.get("evidence_id", ""),
                "source_type": "visual",
                "source_id": "screenshot",
                "product_id": None,
                "content": f"{ve.get('field', '')}: {ve.get('value', '')}",
                "modality": "image",
                "confidence": ve.get("confidence", 0),
            })

    # P4: avoid_tags 降权 — 匹配避雷关键词的商品扣分
    if avoid_tags:
        try:
            for dr in decision_results:
                title = ""
                for p in products:
                    if p.get("product_id") == dr.get("product_id"):
                        title = p.get("title", "")
                        break
                hit = any(kw in title for kw in avoid_tags)
                if hit:
                    dr["final_score"] *= 0.7
                    dr.setdefault("risk_factors", []).append(f"匹配避雷标签: {', '.join(avoid_tags)}")
        except Exception:
            pass

    # Sort by final_score
    paired = list(zip(products, decision_results))
    paired.sort(key=lambda x: x[1]["final_score"], reverse=True)
    products = [p for p, _ in paired]
    decision_results = [d for _, d in paired]

    trace_steps.append({
        "step_id": "T002",
        "agent_name": "V0-TextPipeline",
        "action": "text_retrieve_and_score",
        "input_summary": search_query[:80],
        "output_summary": f"found {len(products)} products",
        "latency_ms": 0,
        "status": "success",
    })

    answer = _build_answer(products[:5], decision_results[:5])

    # P4: 对话提取检查
    if req.user_id:
        try:
            from app.services.user_profile_service import get_user_profile_service
            _svc = get_user_profile_service()
            if _svc.has_long_term_signal(req.user_query):
                updated = await _svc.parse_and_merge(req.user_id, req.user_query)
                if updated:
                    answer = answer.rstrip() + "\n\n我记住了，已更新你的偏好设置。"
        except Exception:
            pass

    fallback_status: dict = {"visual_enabled": req.image_url is not None}
    if visual_result:
        fallback_status["visual_level"] = visual_result.get("fallback_level", 0)
        fallback_status["visual_confidence"] = visual_result.get("confidence", 0)
    else:
        fallback_status["visual_enabled"] = False

    return RecommendResponse(
        session_id=session_id,
        conversation_id=req.conversation_id or "",
        answer=answer,
        products=products,
        evidence_list=evidence_list,
        decision_results=decision_results,
        trace_steps=trace_steps,
        visual_result=visual_result,
        skill_executions=[],
        harness_report={},
        fallback_status=fallback_status,
        used_memories=[],
        blocked_memories=[],
        memory_trace={},
    )


def _parse_constraints(query: str) -> dict:
    from app.decision.rules import detect_category, detect_budget, detect_scenario

    constraints: dict = {}
    category = detect_category(query)
    if category:
        constraints["category"] = category
    budget = detect_budget(query)
    if budget:
        constraints["budget_max"] = budget
    scenario = detect_scenario(query)
    if scenario:
        constraints["scenario"] = scenario
    return constraints


# ---- V2 LangGraph Workflow Endpoint ----

@router.post("/api/recommend/v2", response_model=RecommendResponse)
async def recommend_v2(req: RecommendRequest, actor: Actor = Depends(resolve_public_actor)):
    """V2 Agent Workflow: Router → Retrieval → Decision → Response"""
    from app.workflow.graph import run_workflow
    from app.services.conversation_service import get_conversation_service
    import logging
    _log = logging.getLogger(__name__)

    if isinstance(actor, Actor):
        req.user_id = actor.user_id
    session_id = req.session_id or str(uuid.uuid4())[:8]
    user_id = req.user_id or ""
    conversation_id = req.conversation_id or ""

    # P0: 创建或恢复 conversation (Memory Lite, async)
    conv_svc = get_conversation_service()
    conv_result = await conv_svc.aget_or_create(user_id=user_id, session_id=session_id,
                                                conversation_id=conversation_id)
    conversation_id = conv_result["conversation_id"]

    # P0: 写入 user message
    try:
        await conv_svc.aappend_user_message(
            conversation_id=conversation_id, user_id=user_id,
            session_id=session_id, content=req.user_query,
            image_url=req.image_url or "",
            metadata={"demo_mode": req.demo_mode},
        )
    except Exception as e:
        _log.warning(f"Failed to write user message: {e}")

    # P2: FollowUpEngine 统一追问检测 (best-effort)
    # P2 + P4: FollowUpEngine + Profile 并行加载
    enriched_query = req.user_query
    followup_constraints = {}
    context_prompt = ""
    avoid_tags = []

    async def _v2_followup():
        nonlocal enriched_query, followup_constraints
        try:
            from app.services.followup_engine import get_followup_engine
            engine = get_followup_engine()
            fu = engine.detect(
                conversation_id=conversation_id, session_id=session_id,
                current_query=req.user_query,
            )
            if fu.get("is_follow_up") and fu.get("context_prompt"):
                enriched_query = f"{req.user_query}\n\n{fu['context_prompt']}"
            followup_constraints = fu.get("updated_constraints", {})
            return fu
        except Exception as e:
            _log.debug(f"FollowUpEngine skipped: {e}")
            return {}

    async def _v2_profile():
        try:
            if user_id:
                from app.services.user_profile_service import get_user_profile_service
                return await get_user_profile_service().inject_profile_hints(
                    user_id, query=req.user_query, enriched_query=req.user_query,
                    context_prompt="",
                )
        except Exception:
            pass
        return {"enriched_query": req.user_query, "context_prompt": "", "avoid_tags": []}

    import asyncio as _asyncio
    follow_up_ctx, hints_result = await _asyncio.gather(_v2_followup(), _v2_profile())
    context_prompt = (follow_up_ctx.get("context_prompt", "") + "\n" + hints_result["context_prompt"]).strip()
    if enriched_query == req.user_query:
        enriched_query = hints_result["enriched_query"]
    avoid_tags = hints_result["avoid_tags"]

    # 构建约束预填（FollowUpEngine 检测到的追问约束 + profile avoid_tags）
    prefill = None
    if followup_constraints or avoid_tags:
        from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
        prefill = WorkflowState(
            constraints=Constraints(
                category=followup_constraints.get("category"),
                sub_category=followup_constraints.get("sub_category"),
                budget_max=followup_constraints.get("budget_max"),
                budget_min=followup_constraints.get("budget_min"),
                scenario=followup_constraints.get("scenario"),
                exclude_tags=list(avoid_tags),
            ),
            retrieval_plan=RetrievalPlan(
                channels=["text", "review", "policy"],
                category=followup_constraints.get("category"),
                sub_category=followup_constraints.get("sub_category"),
            ),
        )

    result = await run_workflow(
        user_query=req.user_query,
        image_url=req.image_url,
        session_id=session_id,
        user_id=user_id,
        conversation_id=conversation_id,
        prefill_state=prefill,
        context_prompt=context_prompt,
    )
    result.session_id = session_id

    # P0: 写入 assistant message
    product_ids = [p.get("product_id", "") for p in result.retrieved_products[:10]]
    try:
        evidence_ids = [e.get("evidence_id", "") for e in result.evidence_list[:10]]
        await conv_svc.aappend_assistant_message(
            conversation_id=conversation_id, user_id=user_id,
            session_id=session_id, content=result.answer,
            product_refs=product_ids,
            evidence_refs=evidence_ids,
        )
    except Exception as e:
        _log.warning(f"Failed to write assistant message: {e}")

    # P2: 更新 context_snapshot（含追问上下文 + Router 品类持久化）
    snapshot_update = {
        "last_query": req.user_query,
        "last_recommended_product_ids": product_ids,
        "last_answer": result.answer[:200],
    }
    if follow_up_ctx["is_follow_up"]:
        snapshot_update["last_follow_up_type"] = follow_up_ctx["follow_up_type"]
    updated_budget = follow_up_ctx.get("updated_constraints", {}).get("budget_max")
    if updated_budget:
        snapshot_update["budget_max"] = updated_budget
    # 持久化 Router 检测到的品类，供下一轮 FollowUpEngine 继承
    if result.constraints:
        c = result.constraints
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
    try:
        await conv_svc.aupdate_context_snapshot(conversation_id, snapshot_update)
    except Exception as e:
        _log.debug(f"Context snapshot update skipped: {e}")

    # P4: 对话提取检查 — 用户消息含长时信号则异步提取偏好
    try:
        if user_id:
            from app.services.user_profile_service import get_user_profile_service
            profile_svc = get_user_profile_service()
            if profile_svc.has_long_term_signal(req.user_query):
                profile = await profile_svc.parse_and_merge(user_id, req.user_query)
                if profile:
                    result.answer = result.answer.rstrip() + "\n\n我记住了，已更新你的偏好设置。"
    except Exception as e:
        _log.debug(f"Conversation memory extraction skipped: {e}")

    # P4: 异步上下文压缩 — 不阻塞响应，后台更新 conversation_summary
    if conversation_id and user_id:
        try:
            import asyncio
            prev_summary = ""
            try:
                snap = conv_svc.get_context_snapshot_sync(conversation_id)
                prev_summary = (snap or {}).get("conversation_summary", "") or ""
            except Exception:
                pass
            asyncio.create_task(
                _compress_conversation(conversation_id, conv_svc, prev_summary,
                                       req.user_query, result.answer)
            )
        except Exception:
            pass

    return RecommendResponse(
        session_id=session_id,
        conversation_id=conversation_id,
        answer=result.answer,
        products=result.retrieved_products,
        evidence_list=result.evidence_list,
        decision_results=result.decision_results,
        trace_steps=result.trace_steps,
        visual_result=result.visual_result,
        skill_executions=result.skill_executions,
        harness_report=result.harness_report,
        fallback_status=result.fallback_status,
        retrieval_plan=result.retrieval_plan.model_dump() if result.retrieval_plan else None,
        sufficiency_report=result.sufficiency_report,
        constraints=result.constraints.model_dump() if result.constraints else None,
        used_memories=result.used_memories,
        blocked_memories=result.blocked_memories,
        memory_trace=result.memory_trace,
        needs_clarification=result.needs_clarification,
        clarification_question=result.clarification_question,
        clarification_options=result.clarification_options,
        timing=result.timing,
    )


async def _compress_conversation(
    cid: str, conv_svc, prev_summary: str,
    last_query: str, last_answer: str, pending_question: str | None = None,
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
        pass


# ---- 约束引导式推荐 ----

class GuideRequest(BaseModel):
    user_query: str
    session_id: str = ""
    user_id: str = ""
    conversation_id: str = ""
    category: str = ""
    sub_category: str = ""
    concern: str = ""
    budget_max: float | None = None
    budget_min: float | None = None
    round_num: int = 0  # 已追问轮数


class GuideResponse(BaseModel):
    session_id: str
    conversation_id: str = ""
    answer: str
    should_recommend: bool = False
    options: list[dict] = []  # [{label, value, dim}]
    locked_category: str = ""
    locked_sub_category: str = ""
    locked_concern: str = ""
    budget_max: float | None = None
    budget_min: float | None = None
    # 当 should_recommend=True 时填充以下字段
    products: list[dict] = []
    decision_results: list[dict] = []
    evidence_list: list[dict] = []
    trace_steps: list[dict] = []


@router.post("/api/recommend/guide", response_model=GuideResponse)
async def recommend_guide(req: GuideRequest, actor: Actor = Depends(resolve_public_actor)):
    """约束引导式推荐: 每次返回下一轮追问或最终推荐结果。"""
    from app.services.constraint_guide import get_constraint_guide

    if isinstance(actor, Actor):
        req.user_id = actor.user_id
    session_id = req.session_id or str(uuid.uuid4())[:8]

    # P4: 加载长期偏好画像（预填约束 + 后续注入检索/上下文）
    profile = None
    if req.user_id:
        try:
            from app.services.user_profile_service import get_user_profile_service
            _p_svc = get_user_profile_service()
            profile = await _p_svc.get_profile(req.user_id)
        except Exception:
            pass

    # 从 profile 预填缺失的约束
    if profile and profile.get("enabled", True):
        if not category and profile.get("categories"):
            category = profile["categories"][0]
        if not budget_max and profile.get("budget_max"):
            budget_max = profile["budget_max"]
        if not budget_min and profile.get("budget_min"):
            budget_min = profile["budget_min"]

    # 从 query 中检测 category (如果还没锁定)
    category = req.category
    if not category:
        from app.decision.rules import detect_category
        category = detect_category(req.user_query) or ""

    # 从 query 中检测 sub_category
    sub_category = req.sub_category
    if not sub_category and category:
        from app.decision.rules import detect_sub_category
        sub_category = detect_sub_category(req.user_query, category) or ""

    # 从 query 中检测 budget
    budget_max = req.budget_max
    budget_min = req.budget_min
    if budget_max is None and budget_min is None:
        from app.decision.rules import detect_budget
        budget_max = detect_budget(req.user_query)

    # 从 query 中检测 concern
    concern = req.concern
    if not concern and category:
        from app.services.constraint_guide import CONCERN_KEYWORDS
        import re
        keywords = CONCERN_KEYWORDS.get(category, [])
        for label, pattern in keywords:
            if re.search(pattern, req.user_query, re.IGNORECASE):
                concern = label
                break

    # 判断 query 是否本身已足够具体
    # 如果 sub_category 从本轮 query 检测到 (非上轮锁定) → 加速：跳过品类追问
    sub_from_query = bool(sub_category and not req.sub_category)
    fast_track = sub_from_query and req.round_num == 0

    if fast_track:
        # 已有子品类 → 直接问预算 (如果没指定) 或推荐
        if budget_max is None and budget_min is None:
            budget_opts = get_constraint_guide()._get_budget_options(category, sub_category)
            if len(budget_opts) >= 2:
                return GuideResponse(
                    session_id=session_id,
                    conversation_id=req.conversation_id or "",
                    answer="你的预算大概是多少？",
                    should_recommend=False,
                    options=[{"label": o.label, "value": o.value, "dim": o.dim} for o in budget_opts],
                    locked_category=category,
                    locked_sub_category=sub_category,
                    locked_concern=concern,
                    budget_max=budget_max,
                    budget_min=budget_min,
                )
        # 预算也有了 → 直接推荐
        result_guide = get_constraint_guide().guide(
            user_query=req.user_query, category=category, sub_category=sub_category,
            concern=concern, budget_max=budget_max, budget_min=budget_min, round_num=99,
        )
        result_guide.should_recommend = True
    else:
        result_guide = get_constraint_guide().guide(
            user_query=req.user_query,
            category=category,
            sub_category=sub_category,
            concern=concern,
            budget_max=budget_max,
            budget_min=budget_min,
            round_num=req.round_num,
        )

    if not result_guide.should_recommend:
        return GuideResponse(
            session_id=session_id,
            conversation_id=req.conversation_id or "",
            answer=result_guide.answer,
            should_recommend=False,
            options=[{"label": o.label, "value": o.value, "dim": o.dim} for o in result_guide.options],
            locked_category=result_guide.locked_category,
            locked_sub_category=result_guide.locked_sub_category,
            locked_concern=result_guide.locked_concern,
            budget_max=result_guide.budget_max,
            budget_min=result_guide.budget_min,
        )

    # 约束足够 → 走完整 V2 工作流，但预填约束让 Router 跳过 LLM 重复解析
    from app.workflow.graph import run_workflow
    from app.schemas.workflow import WorkflowState, Constraints

    enriched_query = req.user_query
    if result_guide.locked_concern:
        enriched_query = f"{enriched_query} {result_guide.locked_concern}"
    if result_guide.locked_sub_category and result_guide.locked_sub_category not in enriched_query:
        enriched_query = f"{enriched_query} {result_guide.locked_sub_category}"

    # P4: 注入 profile search_hints + context_prompt + avoid_tags
    context_prompt = ""
    if profile and profile.get("enabled", True):
        hints_result = await get_user_profile_service().inject_profile_hints(
            req.user_id or "", query=req.user_query, enriched_query=enriched_query,
        )
        enriched_query = hints_result["enriched_query"]
        context_prompt = hints_result["context_prompt"]

    # 构造预填约束的初始状态，Router 检测到已有约束会跳过 LLM
    prefill = WorkflowState(
        session_id=session_id,
        user_id=req.user_id or "",
        conversation_id=req.conversation_id or "",
        user_query=enriched_query,
        constraints=Constraints(
            category=result_guide.locked_category or None,
            sub_category=result_guide.locked_sub_category or None,
            budget_max=result_guide.budget_max,
            budget_min=result_guide.budget_min,
        ),
        intent="recommend",  # 跳过 Router 意图识别
    )

    wf_result = await run_workflow(
        user_query=enriched_query,
        image_url=None,
        session_id=session_id,
        user_id=req.user_id or "",
        conversation_id=req.conversation_id or "",
        prefill_state=prefill,
        context_prompt=context_prompt,
    )

    return GuideResponse(
        session_id=session_id,
        conversation_id=req.conversation_id or "",
        answer=wf_result.answer,
        should_recommend=True,
        locked_category=result_guide.locked_category,
        locked_sub_category=result_guide.locked_sub_category,
        locked_concern=result_guide.locked_concern,
        budget_max=result_guide.budget_max,
        budget_min=result_guide.budget_min,
        products=wf_result.retrieved_products,
        decision_results=wf_result.decision_results,
        evidence_list=wf_result.evidence_list,
        trace_steps=wf_result.trace_steps,
    )


def _build_answer(products: list[dict], results: list[dict]) -> str:
    if not products:
        return "抱歉，没有找到符合您条件的商品。请尝试调整需求。"

    lines = ["根据您的需求，为您找到以下商品："]
    for i, (p, r) in enumerate(zip(products, results), 1):
        score = r.get("display_score", 0)
        cat_tag = f"[{p.get('category', '')}/{p.get('sub_category', '')}]"
        lines.append(f"\n{i}. {cat_tag} {p['title']} - ¥{p['price']}")
        lines.append(f"   推荐分 {score}/10")
        reason = r.get("recommendation_reason", "")
        if reason:
            lines.append(f"   {reason}")
        risks = r.get("risk_factors", [])
        if risks:
            lines.append(f"   ⚠ {', '.join(risks)}")

    return "\n".join(lines)
