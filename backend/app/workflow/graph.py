"""V1 LangGraph Workflow — 5-Agent 购物决策编排。

工作流:
  START → Router → [Visual?] → Retrieval → [Reranker?] → Decision → Response → END

LangGraph StateGraph 控制状态流转，每个 Agent 是一个 node。
"""

import asyncio
import time
from langgraph.graph import StateGraph, END

from app.agents.router_agent import RouterAgent
from app.agents.visual_agent import VisualAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.decision_agent import DecisionAgent
from app.agents.response_agent import ResponseAgent
from app.model_gateway.gateway import get_model_gateway
from app.verification.response_guard import ResponseGuard
from app.verification.evidence_checker import EvidenceSufficiencyChecker
from app.workflow.checkpoint import get_checkpoint_store
from app.services.conversation_service import get_conversation_service
from app.repositories.product_repo import get_product_repo
from app.schemas.workflow import WorkflowState
from app.core.cache import cached, make_key, cache_set
from app.core.config import REDIS_CACHE_TTL_WORKFLOW
import json
import logging
_log = logging.getLogger(__name__)

# 全局单例 — 通过 factory 注入 repo，PG/JSON 自动切换
_product_repo = get_product_repo()
_router = RouterAgent()
_visual = VisualAgent()
_retrieval = RetrievalAgent(repo=_product_repo)
_decision = DecisionAgent(repo=_product_repo)
_response = ResponseAgent()
_gateway = get_model_gateway()
_guard = ResponseGuard()
_evidence_checker = EvidenceSufficiencyChecker()


async def _node_router(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()

    # 有图片时：Router 和 Visual 并行（两者无依赖）
    visual_task = None
    if state.image_url:
        visual_task = asyncio.create_task(_visual.parse(state.image_url, state.user_query))

    state = await _router.execute(state)
    state.timing["router_ms"] = round((time.perf_counter() - t0) * 1000)

    # 等待并行 Visual 结果
    if visual_task:
        try:
            state._visual_prefetch = await visual_task
        except Exception:
            state._visual_prefetch = None

    # Memory Lite: 约束合并 → context_snapshot (ConversationService 统一管理)
    conv_svc = get_conversation_service()
    if state.conversation_id:
        try:
            state.constraints = await conv_svc.merge_constraints(
                state.conversation_id, state.constraints
            )
            await conv_svc.set_last_context(
                state.conversation_id,
                query=state.user_query,
                intent=state.intent,
            )
        except Exception as e:
            _log.debug(f"Constraint merge skipped: {e}")

    return state


async def _node_visual(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    if not state.image_url:
        state.timing["visual_ms"] = 0
        return state

    # 优先用 Router 并行预取的结果
    result = getattr(state, '_visual_prefetch', None)
    if result is not None:
        delattr(state, '_visual_prefetch')
    else:
        result = await _visual.parse(state.image_url, state.user_query)
    if result:
        # 归一化为 dict（缓存命中返回 VisualResult，反序列化器已修复）
        vr = result if isinstance(result, dict) else result.model_dump()
        state.visual_result = vr
        p_name = vr.get("product_name", "") or ""
        p_brand = vr.get("brand", "") or ""
        p_cat = vr.get("category", "") or ""
        p_price = vr.get("price")
        p_specs = vr.get("specs", "") or ""
        p_conf = vr.get("confidence", 0) or 0

        # 视觉信息注入：高置信度精确匹配，低置信度引导搜索
        if p_conf >= 0.2:
            extra_info = [x for x in [p_name, p_brand, p_cat, p_specs] if x]
            if extra_info:
                state.user_query = f"{state.user_query} {' '.join(extra_info)}"

            # ① 品类覆盖：以视觉为准，无条件清空旧约束防止泄漏
            mapped_cat = _map_visual_category(p_cat) if p_cat else ""
            if mapped_cat:
                state.constraints.category = mapped_cat
                state.constraints.sub_category = p_cat or ""
            # 有视觉结果时清空旧场景/预算（防止上一轮泄漏）
            state.constraints.scenario = None
            state.constraints.scenario_keywords = []
            state.constraints.budget_min = None
            state.constraints.budget_max = None

            # ② 精确匹配：仅高置信度(≥0.5)执行，低置信度跳过（同类推荐即可）
            if p_conf >= 0.5:
                try:
                    from app.core.database import get_session_sync
                    from app.models.product import ProductModel
                    from sqlalchemy import select, or_, func
                    factory = get_session_sync()
                    if factory:
                        async with factory() as session:
                            conditions = []
                            if p_brand and len(p_brand) >= 2 and not (p_brand.isascii() and len(p_brand) <= 3 and p_brand.isalpha()):
                                conditions.append(ProductModel.brand.ilike(f"%{p_brand}%"))
                            for window in [3, 2]:
                                for i in range(len(p_name) - window + 1):
                                    kw = p_name[i:i + window]
                                    if kw and len(kw) >= 2:
                                        conditions.append(ProductModel.title.ilike(f"%{kw}%"))
                            if conditions:
                                result = await session.execute(
                                    select(ProductModel.product_id)
                                    .where(or_(*conditions))
                                    .limit(5)
                                )
                                pids = [row[0] for row in result.fetchall()]
                                state.visual_matched_pids = pids[:2]
                except Exception:
                    pass

        # 记录 trace
        step_num = len(state.trace_steps) + 1
        state.trace_steps.append({
            "step_id": f"T{step_num:03d}",
            "agent_name": "Visual Agent (Qwen-VL)",
            "action": "image_parse",
            "input_summary": state.image_url[-30:],
            "output_summary": f"product={p_name}, brand={p_brand}, confidence={p_conf}",
            "latency_ms": 0,
            "status": "success" if p_conf > 0 else "fallback",
        })
        state.timing["visual_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


def _map_visual_category(cat: str) -> str:
    mapping = {
        # 美妆护肤
        "精华": "美妆护肤", "面霜": "美妆护肤", "防晒": "美妆护肤", "粉底": "美妆护肤",
        "粉底液": "美妆护肤", "口红": "美妆护肤", "唇釉": "美妆护肤", "面膜": "美妆护肤",
        "洁面": "美妆护肤", "化妆水": "美妆护肤", "爽肤水": "美妆护肤", "眼霜": "美妆护肤",
        "卸妆": "美妆护肤", "眉笔": "美妆护肤", "蜜粉": "美妆护肤", "散粉": "美妆护肤",
        "护肤品": "美妆护肤", "彩妆": "美妆护肤",
        # 数码电子
        "手机": "数码电子", "智能手机": "数码电子", "电脑": "数码电子", "笔记本": "数码电子",
        "笔记本电脑": "数码电子", "耳机": "数码电子", "真无线耳机": "数码电子", "蓝牙耳机": "数码电子",
        "充电宝": "数码电子", "移动电源": "数码电子", "平板": "数码电子", "平板电脑": "数码电子",
        "充电器": "数码电子", "数据线": "数码电子", "键盘": "数码电子", "鼠标": "数码电子",
        "音箱": "数码电子", "手表": "数码电子",
        # 服饰运动
        "T恤": "服饰运动", "短袖": "服饰运动", "短袖T恤": "服饰运动", "速干T恤": "服饰运动",
        "跑鞋": "服饰运动", "跑步鞋": "服饰运动", "篮球鞋": "服饰运动", "运动鞋": "服饰运动",
        "徒步鞋": "服饰运动", "登山鞋": "服饰运动", "裤子": "服饰运动", "运动长裤": "服饰运动",
        "运动短裤": "服饰运动", "户外裤": "服饰运动", "瑜伽裤": "服饰运动", "紧身裤": "服饰运动",
        "卫衣": "服饰运动", "背包": "服饰运动", "双肩包": "服饰运动", "帽子": "服饰运动",
        "棒球帽": "服饰运动",
        # 食品饮料
        "零食": "食品饮料", "坚果": "食品饮料", "饮料": "食品饮料", "咖啡": "食品饮料",
        "速溶咖啡": "食品饮料", "茶叶": "食品饮料", "茶饮": "食品饮料", "牛奶": "食品饮料",
        "酸奶": "食品饮料", "气泡水": "食品饮料", "碳酸饮料": "食品饮料", "功能饮料": "食品饮料",
        "方便面": "食品饮料", "方便食品": "食品饮料", "调味品": "食品饮料", "酱油": "食品饮料",
        "矿泉水": "食品饮料", "可乐": "食品饮料",
    }
    # 模糊匹配：子串命中即可
    for k, v in mapping.items():
        if k in cat:
            return v
    return ""


async def _node_retrieval(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    result = await _retrieval.execute(state)
    # RAG trace: 记录 embedding 搜索结果
    try:
        from app.observability.rag_logger import RagTrace
        _rag = RagTrace(session_id=state.session_id or "", query=state.user_query)
        _rag.set_embedding(
            query_vec=[],  # 向量在检索内部，不暴露
            candidates=result.retrieved_products or [],
            latency_ms=round((time.perf_counter() - t0) * 1000),
        )
        state._rag_trace = _rag
    except Exception:
        pass
    # 视觉精确匹配：将匹配到的商品钉在检索结果顶部
    visual_pids = getattr(state, "visual_matched_pids", None) or []
    if visual_pids:
        products = result.retrieved_products
        matched = [p for p in products if p.get("product_id") in visual_pids]
        others = [p for p in products if p.get("product_id") not in visual_pids]
        result.retrieved_products = matched + others
        # 同时给匹配商品加分，确保精排不翻盘
        for p in matched:
            p["reranker_score"] = max(p.get("reranker_score", 0), 0.95)
            p["_visual_exact_match"] = True
    # 避雷硬过滤: 从检索结果中移除匹配 exclude_tags 的商品
    exclude_tags = getattr(state.constraints, "exclude_tags", None) or []
    if exclude_tags and result.retrieved_products:
        before = len(result.retrieved_products)
        result.retrieved_products = [
            p for p in result.retrieved_products
            if not any(
                tag.lower() in (p.get("title", "") + p.get("brand", "")).lower()
                for tag in exclude_tags
            )
        ]
        filtered = before - len(result.retrieved_products)
        if filtered:
            _log.info(f"Hard-excluded {filtered} products matching exclude_tags: {exclude_tags}")

    # 检索完成后恢复原始 query（仅限 profile hints 污染，视觉信息保留给精排和回复）
    if getattr(state, "user_query_original", None):
        state.user_query = state.user_query_original
        state.user_query_original = None
    result.timing["retrieval_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


async def _node_reranker(state: WorkflowState) -> WorkflowState:
    """Qwen Reranker 精排：对语义检索结果进行语义重排序"""
    t0 = time.perf_counter()
    products = state.retrieved_products
    # 快速模式：跳过 Reranker LLM 调用
    if state.context_prompt and "[FAST_MODE]" in (state.context_prompt or ""):
        state.timing["rerank_ms"] = 0
        return state
    if len(products) <= 1:
        state.timing["rerank_ms"] = 0
        return state

    try:
        # Build evidence lookup by product_id for richer reranker input
        ev_by_pid: dict[str, list[str]] = {}
        for ev in state.evidence_list:
            pid = ev.get("product_id", "")
            content = ev.get("content", "")
            if pid and content and "余弦相似度" not in str(content) and "Text match" not in str(content):
                ev_by_pid.setdefault(pid, []).append(str(content)[:300])

        documents = []
        for p in products:
            pid = p.get("product_id", "")
            doc = f"{p.get('title','')} {p.get('category','')} {p.get('sub_category','')}"
            desc = p.get('description', '')
            if desc:
                doc += f" {desc[:300]}"
            # Add rag_knowledge content for richer semantic matching
            rk = p.get("rag_knowledge") or {}
            if isinstance(rk, dict):
                mkt = rk.get("marketing_description", "")
                if mkt:
                    doc += f" {str(mkt)[:300]}"
                faqs = rk.get("official_faq", [])
                if isinstance(faqs, list):
                    for faq in faqs[:2]:
                        if isinstance(faq, dict):
                            doc += f" {faq.get('question','')[:150]} {faq.get('answer','')[:300]}"
                revs = rk.get("user_reviews", [])
                if isinstance(revs, list):
                    for rev in revs[:2]:
                        if isinstance(rev, dict):
                            doc += f" 用户评价: {rev.get('content','')[:200]}"
            # Add evidence snippets
            ev_snippets = ev_by_pid.get(pid, [])[:2]
            if ev_snippets:
                doc += " " + " ".join(ev_snippets)
            documents.append(doc)

        ranked = await _gateway.rerank(
            query=state.user_query,
            documents=documents,
            top_n=len(products),
        )

        # 按 relevance_score 降序重排，同时把分数写回每个 product dict
        index_map = {r["index"]: r["relevance_score"] for r in ranked}
        # 固定校准: Reranker 排序分(0~1) → 商业可读分，保留质量信号和区分度
        for idx in index_map:
            index_map[idx] = 0.68 + 0.38 * index_map[idx]
        reordered = sorted(
            enumerate(products),
            key=lambda x: index_map.get(x[0], 0.0),
            reverse=True,
        )
        # 将 reranker_score 写入 product dict，供 Decision V4 scoring 使用
        for idx, p in enumerate(products):
            p["reranker_score"] = index_map.get(idx, 0.0)
            p["relevance_score"] = p["reranker_score"]
        state.retrieved_products = [p for _, p in reordered]
        # 视觉精确匹配商品锁定最高分（Reranker 可能覆盖了之前的加分）
        visual_pids = set(state.visual_matched_pids or [])
        for p in state.retrieved_products:
            if p.get("product_id") in visual_pids:
                p["reranker_score"] = 0.99
                p["relevance_score"] = 0.99

        # 记录 trace
        step_num = len(state.trace_steps) + 1
        state.trace_steps.append({
            "step_id": f"T{step_num:03d}",
            "agent_name": "Qwen Reranker",
            "action": "semantic_rerank",
            "input_summary": f"{len(products)} candidates",
            "output_summary": f"reranked, top3 scores: {[f'{index_map.get(i,0):.3f}' for i in range(min(3,len(products)))]}",
            "latency_ms": 0,
            "status": "success",
        })
    except Exception as e:
        _log.warning(f"Reranker unavailable, falling back to raw retrieval scores: {e}")

    # RAG trace: 记录 reranker 结果
    try:
        _rag = getattr(state, "_rag_trace", None)
        if _rag is not None:
            _rag.set_reranker(
                input_products=products,
                ranked=state.retrieved_products,
                scores=[p.get("reranker_score", 0) for p in state.retrieved_products],
                latency_ms=round((time.perf_counter() - t0) * 1000),
            )
    except Exception:
        pass
    state.timing["rerank_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


async def _node_decision(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    state = await _decision.execute(state)
    # 按 final_score 排序，但视觉精确匹配商品始终排在最前
    if state.decision_results and state.retrieved_products:
        ranked = {r["product_id"]: i for i, r in enumerate(state.decision_results)}
        visual_pids = set(state.visual_matched_pids or [])
        state.retrieved_products.sort(key=lambda p: (
            0 if p.get("product_id") in visual_pids else 1,  # 精确匹配优先
            ranked.get(p.get("product_id", ""), 999)          # 同组内按分数排
        ))
        state.evidence_list.sort(key=lambda e: ranked.get(e.get("product_id", ""), 999))
    # Memory Lite: 结构化商品列表存入 context_snapshot (供 FollowUpEngine 指代解析)
    if state.conversation_id and state.retrieved_products:
        try:
            structured = []
            for p in state.retrieved_products[:10]:
                pid = p.get("product_id", "")
                if pid:
                    structured.append({
                        "product_id": pid,
                        "title": p.get("title", "")[:60],
                        "brand": p.get("brand", ""),
                        "price": p.get("price", 0),
                    })
            if structured:
                conv_svc = get_conversation_service()
                await conv_svc.set_last_products(state.conversation_id, structured)
        except Exception:
            pass
    # RAG trace: 记录最终结果 + 评估
    try:
        _rag = getattr(state, "_rag_trace", None)
        if _rag is not None:
            _rag.set_final(state.retrieved_products or [], state.decision_results or [])
            _rag.evaluate()  # 尝试从 eval_queries 匹配 golden
            _rag.save()
    except Exception:
        pass
    state.timing["decision_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


async def _node_response(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    result = await _response.execute(state)
    result.timing["response_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


def _node_evidence_check(state: WorkflowState) -> WorkflowState:
    """证据充足性检查：在 Reranker 之后、Decision 之前执行。"""
    t0 = time.perf_counter()
    state.sufficiency_report = _evidence_checker.check(state)
    step_num = len(state.trace_steps) + 1
    state.trace_steps.append({
        "step_id": f"T{step_num:03d}",
        "agent_name": "Evidence Sufficiency Checker",
        "action": "evidence_check",
        "input_summary": f"{state.sufficiency_report.get('total_evidence', 0)} evidence items",
        "output_summary": "sufficient" if state.sufficiency_report.get("sufficient")
                          else f"missing: {state.sufficiency_report.get('missing_types', [])}",
        "latency_ms": 0,
        "status": "pass" if state.sufficiency_report.get("sufficient") else "insufficient",
    })
    state.timing["evidence_check_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


def _node_guard(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    _guard.check(state)  # sets state.harness_report with individual checks + passed

    response_passed = state.harness_report.get("passed", True)
    state.harness_report["passed"] = response_passed
    state.harness_report["failure_source"] = None if response_passed else "response_guard"

    state.timing["guard_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


def _router_next(state: WorkflowState) -> str:
    """Router 后决定下一节点：有图优先视觉解析，闲聊且无图→直接回复，否则→检索"""
    if state.image_url:
        return "visual"
    if state.intent == "chitchat":
        return "response"
    return "retrieval"


def _has_results(state: WorkflowState) -> str:
    return "decision" if state.retrieved_products else "response"


def build_workflow() -> StateGraph:
    workflow = StateGraph(WorkflowState)

    workflow.add_node("router", _node_router)
    workflow.add_node("visual", _node_visual)
    workflow.add_node("retrieval", _node_retrieval)
    workflow.add_node("reranker", _node_reranker)
    workflow.add_node("evidence_check", _node_evidence_check)
    workflow.add_node("decision", _node_decision)
    workflow.add_node("response", _node_response)
    workflow.add_node("guard", _node_guard)

    workflow.set_entry_point("router")

    workflow.add_conditional_edges("router", _router_next,
                                   {"visual": "visual", "retrieval": "retrieval", "response": "response"})
    workflow.add_edge("visual", "retrieval")
    workflow.add_edge("retrieval", "reranker")
    workflow.add_edge("reranker", "evidence_check")
    workflow.add_conditional_edges("evidence_check", _has_results,
                                   {"decision": "decision", "response": "response"})
    workflow.add_edge("decision", "response")
    workflow.add_edge("response", "guard")
    workflow.add_edge("guard", END)

    return workflow


_compiled = None


def get_workflow():
    global _compiled
    if _compiled is None:
        _compiled = build_workflow().compile()
    return _compiled


_compiled_no_response = None


def get_workflow_no_response():
    """无 response/guard 节点的 workflow — 供 SSE 流式路径使用。"""
    global _compiled_no_response
    if _compiled_no_response is None:
        wf = build_workflow()
        # 移除 response 和 guard，decision 直接到 END
        # LangGraph 的 StateGraph 在 compile 前可以修改
        wf.add_edge("decision", END)
        _compiled_no_response = wf.compile()
    return _compiled_no_response


async def run_workflow(user_query: str, image_url: str | None = None, session_id: str = "",
                      user_id: str = "", conversation_id: str = "", enable_checkpoint: bool = True,
                      prefill_state: WorkflowState | None = None,
                      context_prompt: str = "", no_response: bool = False,
                      fast_mode: bool = False) -> WorkflowState:
    wf = get_workflow_no_response() if no_response else get_workflow()

    # ---- Workflow 级缓存：相同 query + image 在 TTL 内直接返回 ----
    cache_key = make_key("workflow", user_query, image_url or "noimg", user_id, session_id)
    if not enable_checkpoint:
        state = await _run_uncached(user_query, image_url, session_id, user_id, conversation_id, wf, enable_checkpoint, prefill_state, context_prompt, fast_mode)
    else:
        async def _do_run():
            return await _run_uncached(user_query, image_url, session_id, user_id, conversation_id, wf, enable_checkpoint, prefill_state, context_prompt, fast_mode)

        state = await cached(
            cache_key, REDIS_CACHE_TTL_WORKFLOW, _do_run,
            serializer=lambda v: json.dumps(v.model_dump(), ensure_ascii=False, default=str),
            deserializer=lambda s: WorkflowState(**json.loads(s)),
        )

    # cached() may return dict on cache hit; ensure WorkflowState
    if isinstance(state, dict):
        state = WorkflowState(**state)

    return state


async def _run_uncached(user_query: str, image_url: str | None, session_id: str,
                        user_id: str, conversation_id: str, wf, enable_checkpoint: bool,
                        prefill_state: WorkflowState | None = None,
                        context_prompt: str = "", fast_mode: bool = False) -> WorkflowState:
    # 快速模式：context_prompt 前缀标记，Router 和 Reranker 节点读取
    if fast_mode:
        context_prompt = "[FAST_MODE]" + (context_prompt or "")
    if prefill_state is not None:
        state = prefill_state
        state.user_query = user_query
        state.image_url = image_url
        state.context_prompt = context_prompt
    else:
        state = WorkflowState(session_id=session_id or "", user_id=user_id, conversation_id=conversation_id,
                              user_query=user_query, image_url=image_url, context_prompt=context_prompt)

    if enable_checkpoint and state.session_id:
        try:
            ckpt = get_checkpoint_store()
            restored = ckpt.load(state.session_id)
            if restored and restored.user_query == user_query:
                _log.info(f"Resumed from checkpoint: {state.session_id}")
                state = restored
        except Exception as e:
            _log.debug(f"Checkpoint restore skipped: {e}")

    # 使用 ainvoke 以支持 async node（Visual / Retrieval）
    result_dict = await wf.ainvoke(state)
    if isinstance(result_dict, dict):
        result = WorkflowState(**result_dict)
    else:
        result = result_dict

    if enable_checkpoint and state.session_id:
        try:
            ckpt = get_checkpoint_store()
            ckpt.save(result.session_id, "guard", result)
        except Exception as e:
            _log.debug(f"Checkpoint save skipped: {e}")


    return result
