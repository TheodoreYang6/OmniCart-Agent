"""V1 LangGraph Workflow — 5-Agent 购物决策编排。

工作流:
  START → Router → [Visual?] → Retrieval → [Reranker?] → Decision → Response → END

LangGraph StateGraph 控制状态流转，每个 Agent 是一个 node。
"""

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
from app.memory.preference_memory import get_memory
from app.repositories.product_repo import get_product_repo
from app.schemas.workflow import WorkflowState
from app.core.cache import cached, make_key, cache_set
from app.core.config import REDIS_CACHE_TTL_WORKFLOW

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


async async def _node_router(state: WorkflowState) -> WorkflowState:
    state = await _router.execute(state)

    # 合并多轮记忆中的偏好
    mem = get_memory()
    state.constraints = mem.merge_constraints(state.session_id, state.constraints)
    mem.update(state.session_id, state.constraints)

    # V2: 合并长期偏好记忆（跨会话学习）
    if state.user_id:
        try:
            from app.memory.long_term import get_long_term_memory
            ltm = get_long_term_memory()
            lt_defaults = ltm.merge_with_session(state.user_id, state.constraints)
            if lt_defaults:
                # 长期偏好的默认值不覆盖当前会话的明确约束
                if not state.constraints.category and lt_defaults.get("category"):
                    state.constraints.category = lt_defaults["category"]
                if state.constraints.budget_max is None and lt_defaults.get("budget_max"):
                    state.constraints.budget_max = lt_defaults["budget_max"]
                if not state.constraints.scenario and lt_defaults.get("scenario"):
                    state.constraints.scenario = lt_defaults["scenario"]
            # 记录这次搜索行为
            await ltm.record_search(
                user_id=state.user_id,
                query=state.user_query,
                category=state.constraints.category or "",
                sub_category=state.constraints.sub_category or "",
            )
        except Exception:
            pass  # 长期记忆失败不影响主链路

    return state


async def _node_visual(state: WorkflowState) -> WorkflowState:
    if not state.image_url:
        return state
    result = await _visual.parse(state.image_url, state.user_query)
    if result:
        state.visual_result = result.model_dump()
        extra_info = []
        if result.product_name:
            extra_info.append(result.product_name)
        if result.brand:
            extra_info.append(result.brand)
        if result.category:
            extra_info.append(result.category)
        if result.specs:
            extra_info.append(result.specs)
        if extra_info:
            state.user_query = f"{state.user_query} {' '.join(extra_info)}"
        # 记录 trace
        step_num = len(state.trace_steps) + 1
        state.trace_steps.append({
            "step_id": f"T{step_num:03d}",
            "agent_name": "Visual Agent (Qwen-VL)",
            "action": "image_parse",
            "input_summary": state.image_url[-30:],
            "output_summary": f"product={result.product_name}, brand={result.brand}, confidence={result.confidence}",
            "latency_ms": 0,
            "status": "success" if result.confidence > 0 else "fallback",
        })
    return state


async def _node_retrieval(state: WorkflowState) -> WorkflowState:
    return await _retrieval.execute(state)


async def _node_reranker(state: WorkflowState) -> WorkflowState:
    """Qwen Reranker 精排：对 jieba 粗排结果进行语义重排序"""
    products = state.retrieved_products
    if len(products) <= 1:
        return state

    try:
        documents = []
        for p in products:
            doc = f"{p.get('title','')} {p.get('category','')} {p.get('sub_category','')}"
            desc = p.get('description', '')
            if desc:
                doc += f" {desc[:200]}"
            documents.append(doc)

        ranked = await _gateway.rerank(
            query=state.user_query,
            documents=documents,
            top_n=len(products),
        )

        # 按 relevance_score 降序重排
        index_map = {r["index"]: r["relevance_score"] for r in ranked}
        reordered = sorted(
            enumerate(products),
            key=lambda x: index_map.get(x[0], 0.0),
            reverse=True,
        )
        state.retrieved_products = [p for _, p in reordered]

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
    except Exception:
        pass  # Reranker 不可用时保持原序

    return state


def _node_decision(state: WorkflowState) -> WorkflowState:
    return _decision.execute(state)


async def _node_response(state: WorkflowState) -> WorkflowState:
    return await _response.execute(state)


def _node_evidence_check(state: WorkflowState) -> WorkflowState:
    """证据充足性检查：在 Reranker 之后、Decision 之前执行。"""
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
    return state


def _node_guard(state: WorkflowState) -> WorkflowState:
    _guard.check(state)
    return state


def _router_next(state: WorkflowState) -> str:
    """Router 后决定下一节点：闲聊→直接回复，有图→视觉解析，否则→检索"""
    if state.intent == "chitchat":
        return "response"
    return "visual" if state.image_url else "retrieval"


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


async def run_workflow(user_query: str, image_url: str | None = None, session_id: str = "",
                      user_id: str = "", enable_checkpoint: bool = True) -> WorkflowState:
    wf = get_workflow()

    # ---- Workflow 级缓存：相同 query + image 在 TTL 内直接返回 ----
    cache_key = make_key("workflow", user_query, image_url or "noimg")
    if not enable_checkpoint:
        state = await _run_uncached(user_query, image_url, session_id, user_id, wf, enable_checkpoint)
    else:
        async def _do_run():
            return await _run_uncached(user_query, image_url, session_id, user_id, wf, enable_checkpoint)

        state = await cached(cache_key, REDIS_CACHE_TTL_WORKFLOW, _do_run)

    return state


async def _run_uncached(user_query: str, image_url: str | None, session_id: str,
                        user_id: str, wf, enable_checkpoint: bool) -> WorkflowState:
    state = WorkflowState(session_id=session_id or "", user_id=user_id, user_query=user_query, image_url=image_url)

    if enable_checkpoint and state.session_id:
        try:
            ckpt = get_checkpoint_store()
            restored = ckpt.load(state.session_id)
            if restored and restored.user_query == user_query:
                logger = __import__('logging').getLogger(__name__)
                logger.info(f"Resumed from checkpoint: {state.session_id}")
                state = restored
        except Exception:
            pass

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
        except Exception:
            pass

    return result
