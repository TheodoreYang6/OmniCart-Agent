"""V1 LangGraph Workflow — 5-Agent 购物决策编排。

工作流:
  START → Router → [Visual?] → Retrieval → [Reranker?] → Decision → Response → END

LangGraph StateGraph 控制状态流转，每个 Agent 是一个 node。
"""

import asyncio
import time
from langgraph.graph import StateGraph, END

from app.framework.agent_manager import AgentManager
from app.core.display import trim_for_grid
from app.providers.agents import builtin as agents_builtin
from app.providers.recall.rerank_fusion import RerankFusion
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
_MEMORY_RECALL_TIMEOUT_SECONDS = 1.5

# 全局单例 — Agent 经 AgentManager 注册表装配（替换硬编码 import + new），
# repo 通过 factory 注入，PG/JSON 自动切换。节点函数仍用 _router/_visual/... 引用，逻辑不变。
_product_repo = get_product_repo()
_agents = AgentManager.default(builtin=lambda: agents_builtin(_product_repo))
_router = _agents.get("router")
_visual = _agents.get("visual")
_retrieval = _agents.get("retrieval")
_decision = _agents.get("decision")
_response = _agents.get("response")
_gateway = get_model_gateway()
_reranker = RerankFusion(_gateway)
_guard = ResponseGuard()
_evidence_checker = EvidenceSufficiencyChecker()


def get_response_agent():
    """暴露 Response Agent 单例 — 供 SSE 真流式路径调 generate_stream。"""
    return _response


def get_response_guard():
    """暴露 ResponseGuard 单例 — 真流式路径流完后补跑 harness 检查。"""
    return _guard


# 可注册路由表（spec §六）：条件边通过名称查找路由函数，支持业务侧覆盖/扩展。
_ROUTES: dict = {}


def register_route(name: str):
    """声明式注册一个条件边路由函数。"""

    def _deco(fn):
        _ROUTES[name] = fn
        return fn

    return _deco


def get_route(name: str):
    """按名获取路由函数。"""
    return _ROUTES[name]


# 可注册能力表已下沉 framework/orchestration/capabilities.py（P0-1 依赖方向治理）：
# graph 是注册方，providers 层子管线按名消费；此处 re-export 保持存量引用兼容。
from app.framework.orchestration.capabilities import (  # noqa: F401
    get_capability,
    register_capability,
)

# supervisor 单次进入的最大派发批次（死循环护栏）
MAX_SUPERVISOR_STEPS = 16


async def _node_router(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    state = await _router.execute(state)
    state.timing["router_ms"] = round((time.perf_counter() - t0) * 1000)

    # 视觉节点已经在 Router 之前产出结构化结果。只把足够可靠的目录大类
    # 作为 Router 的补充约束，绝不改写用户原始 Query 或覆盖用户明确说出的品类。
    visual = state.visual_result or {}
    if isinstance(visual, dict) and float(visual.get("confidence") or 0) >= 0.55:
        visual_category = str(visual.get("category") or "")
        valid_categories = {"数码电子", "美妆护肤", "服饰运动", "食品饮料", "家居用品", "母婴用品", "运动户外", "个护清洁"}
        if visual_category in valid_categories:
            if not state.constraints.category:
                state.constraints.category = visual_category
                state.retrieval_plan.category = visual_category
            if not state.constraints.sub_category and visual.get("sub_category"):
                state.constraints.sub_category = str(visual["sub_category"])
                state.retrieval_plan.sub_category = state.constraints.sub_category

    # Memory Lite: 约束合并 → context_snapshot (ConversationService 统一管理)
    conv_svc = get_conversation_service()
    if state.conversation_id:
        try:
            # “问欧米”已经由可信 product_id 锁定了单品。它的默认任务是介绍
            # 当前商品，而不是重新执行上一轮的购物任务；继承旧预算/旧品类会
            # 把一件正常商品错误标为“未满足本次预算或品类条件”。用户若明确
            # 提出预算、对比或替代，Router 已会把它写进本轮 constraints。
            if state.retrieval_scope != "exact_product":
                state.constraints = await conv_svc.merge_constraints(state.conversation_id, state.constraints)
            await conv_svc.set_last_context(
                state.conversation_id,
                query=state.user_query,
                intent=state.intent,
            )
        except Exception as e:
            _log.debug(f"Constraint merge skipped: {e}")

    # Memory-aware：从 MemoryBank 召回长期偏好 → used_memories，供 Decision 评分消费（spec §四）。
    # 无 user_id / 该品类无偏好条目时为空 → 评分不变（评测 demo 用户无条目，指标不回退）。
    # 动态编排模式同样发布 memories.ready，但召回本身在 Router 以内以严格的
    # 请求级 deadline 完成。此前把任务放到后台、只在 Decision 等待，会因 LangGraph
    # 节点上下文切换或检索耗时变化导致“慢偏好偶尔被采纳、快偏好偶尔丢失”。
    # 真实召回通常远低于 1.5 秒；超时直接空降级，换取确定性与不污染评分。
    from app.framework.blackboard import current_board

    bb = current_board()

    if state.user_id:
        from app.providers.memory import recall_used_memories

        _recall_kwargs = dict(
            user_id=state.user_id,
            query=state.user_query,
            category=state.constraints.category or "",
            conversation_id=state.conversation_id or "",
        )
        if bb is not None:
            try:
                state.used_memories = await asyncio.wait_for(
                    recall_used_memories(**_recall_kwargs), timeout=_MEMORY_RECALL_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                _log.debug("used_memories recall timed out")
                state.used_memories = []
            except Exception as e:  # noqa: BLE001
                _log.debug(f"used_memories recall skipped: {e}")
                state.used_memories = []
            await bb.publish("memories.ready", {"memories": state.used_memories or []}, producer="router")
        else:
            try:
                state.used_memories = await recall_used_memories(**_recall_kwargs)
            except Exception as e:
                _log.debug(f"used_memories recall skipped: {e}")
    elif bb is not None:
        await bb.publish("memories.ready", {"memories": []}, producer="router")

    return state


@register_capability("visual")
async def _node_visual(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    if not state.image_url:
        state.timing["visual_ms"] = 0
        return state

    # 视觉只在此节点执行一次。Router、实体解析和最终答案复用这份结果。
    result = await _visual.parse(state.image_url, state.user_query_original or state.user_query)
    if result:
        # 归一化为 dict（缓存命中返回 VisualResult，反序列化器已修复）
        vr = result if isinstance(result, dict) else result.model_dump()
        state.visual_result = vr
        p_name = vr.get("product_name", "") or ""
        p_brand = vr.get("brand", "") or ""
        p_model = vr.get("model", "") or ""
        p_specs = vr.get("specs", "") or ""
        p_conf = vr.get("confidence", 0) or 0
        try:
            from app.services.visual_catalog_resolver import VisualCatalogResolver

            resolution = await VisualCatalogResolver().resolve(vr)
            state.product_resolution = resolution.payload
            state.retrieval_scope = resolution.payload.get("retrieval_scope", "broad")
            state.resolved_product_ids = list(resolution.payload.get("resolved_product_ids") or [])
            if resolution.payload.get("match_type") in {"exact_product", "product_family"}:
                state.retrieved_products = resolution.products
                state.evidence_list = resolution.evidence
                state.visual_matched_pids = list(state.resolved_product_ids)
        except Exception as exc:  # catalog matching is an enhancement, never an image-upload failure
            _log.warning("visual catalog resolution degraded: %s", exc)

        # 记录 trace
        step_num = len(state.trace_steps) + 1
        state.trace_steps.append(
            {
                "step_id": f"T{step_num:03d}",
                "agent_name": "Visual Agent (Qwen-VL)",
                "action": "image_parse",
                "input_summary": state.image_url[-30:],
                "output_summary": f"product={p_name}, brand={p_brand}, model={p_model}, confidence={p_conf}",
                "latency_ms": 0,
                "status": "success" if p_conf > 0 else "fallback",
            }
        )
        state.timing["visual_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


def _map_visual_category(cat: str) -> str:
    mapping = {
        # 美妆护肤
        "精华": "美妆护肤",
        "面霜": "美妆护肤",
        "防晒": "美妆护肤",
        "粉底": "美妆护肤",
        "粉底液": "美妆护肤",
        "口红": "美妆护肤",
        "唇釉": "美妆护肤",
        "面膜": "美妆护肤",
        "洁面": "美妆护肤",
        "化妆水": "美妆护肤",
        "爽肤水": "美妆护肤",
        "眼霜": "美妆护肤",
        "卸妆": "美妆护肤",
        "眉笔": "美妆护肤",
        "蜜粉": "美妆护肤",
        "散粉": "美妆护肤",
        "护肤品": "美妆护肤",
        "彩妆": "美妆护肤",
        # 数码电子
        "手机": "数码电子",
        "智能手机": "数码电子",
        "电脑": "数码电子",
        "笔记本": "数码电子",
        "笔记本电脑": "数码电子",
        "耳机": "数码电子",
        "真无线耳机": "数码电子",
        "蓝牙耳机": "数码电子",
        "充电宝": "数码电子",
        "移动电源": "数码电子",
        "平板": "数码电子",
        "平板电脑": "数码电子",
        "充电器": "数码电子",
        "数据线": "数码电子",
        "键盘": "数码电子",
        "鼠标": "数码电子",
        "音箱": "数码电子",
        "手表": "数码电子",
        # 服饰运动
        "T恤": "服饰运动",
        "短袖": "服饰运动",
        "短袖T恤": "服饰运动",
        "速干T恤": "服饰运动",
        "跑鞋": "服饰运动",
        "跑步鞋": "服饰运动",
        "篮球鞋": "服饰运动",
        "运动鞋": "服饰运动",
        "徒步鞋": "服饰运动",
        "登山鞋": "服饰运动",
        "裤子": "服饰运动",
        "运动长裤": "服饰运动",
        "运动短裤": "服饰运动",
        "户外裤": "服饰运动",
        "瑜伽裤": "服饰运动",
        "紧身裤": "服饰运动",
        "卫衣": "服饰运动",
        "背包": "服饰运动",
        "双肩包": "服饰运动",
        "帽子": "服饰运动",
        "棒球帽": "服饰运动",
        # 食品饮料
        "零食": "食品饮料",
        "坚果": "食品饮料",
        "饮料": "食品饮料",
        "咖啡": "食品饮料",
        "速溶咖啡": "食品饮料",
        "茶叶": "食品饮料",
        "茶饮": "食品饮料",
        "牛奶": "食品饮料",
        "酸奶": "食品饮料",
        "气泡水": "食品饮料",
        "碳酸饮料": "食品饮料",
        "功能饮料": "食品饮料",
        "方便面": "食品饮料",
        "方便食品": "食品饮料",
        "调味品": "食品饮料",
        "酱油": "食品饮料",
        "矿泉水": "食品饮料",
        "可乐": "食品饮料",
        # 家居用品
        "保温杯": "家居用品",
        "水杯": "家居用品",
        "四件套": "家居用品",
        "床品": "家居用品",
        "枕头": "家居用品",
        "被子": "家居用品",
        "毛巾": "家居用品",
        "收纳盒": "家居用品",
        "锅具": "家居用品",
        "炒锅": "家居用品",
        "餐具": "家居用品",
        "砧板": "家居用品",
        "台灯": "家居用品",
        "香薰": "家居用品",
        "花瓶": "家居用品",
        # 母婴用品
        "纸尿裤": "母婴用品",
        "尿不湿": "母婴用品",
        "奶瓶": "母婴用品",
        "奶嘴": "母婴用品",
        "婴儿推车": "母婴用品",
        "安全座椅": "母婴用品",
        "婴儿湿巾": "母婴用品",
        "婴儿床": "母婴用品",
        "绘本": "母婴用品",
        "积木": "母婴用品",
        # 运动户外
        "帐篷": "运动户外",
        "睡袋": "运动户外",
        "登山杖": "运动户外",
        "瑜伽垫": "运动户外",
        "哑铃": "运动户外",
        "跳绳": "运动户外",
        "篮球": "运动户外",
        "足球": "运动户外",
        "羽毛球拍": "运动户外",
        "泳镜": "运动户外",
        "滑板": "运动户外",
        # 个护清洁
        "洗发水": "个护清洁",
        "护发素": "个护清洁",
        "沐浴露": "个护清洁",
        "身体乳": "个护清洁",
        "牙膏": "个护清洁",
        "牙刷": "个护清洁",
        "洗衣液": "个护清洁",
        "吹风机": "个护清洁",
        "剃须刀": "个护清洁",
        "卫生巾": "个护清洁",
    }
    # 模糊匹配：子串命中即可
    for k, v in mapping.items():
        if k in cat:
            return v
    return ""


@register_capability("retrieval")
async def _node_retrieval(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    # 商品聚焦入口会带着由 catalog id 解析出的受信任范围进入图。这里直接
    # 复用该范围，避免再跑一轮向量/BM25 后才覆盖结果；也保证后续节点永远
    # 看不到范围外的候选。
    locked_ids = list(state.resolved_product_ids or [])
    if state.retrieval_scope in {"exact_product", "product_family"} and locked_ids:
        locked = [p for p in (state.retrieved_products or []) if p.get("product_id") in locked_ids]
        if locked:
            state.retrieved_products = locked
            state.evidence_list = [e for e in (state.evidence_list or []) if e.get("product_id") in set(locked_ids)]
            state.visual_matched_pids = locked_ids
            state.trace_steps.append(
                {
                    "step_id": f"T{len(state.trace_steps) + 1:03d}",
                    "agent_name": "Product Entity Resolver",
                    "action": "reuse_catalog_identity_lock",
                    "input_summary": (state.user_query_original or state.user_query)[:80],
                    "output_summary": f"{state.retrieval_scope}: {locked_ids}",
                    "latency_ms": 0,
                    "status": "success",
                }
            )
            state.timing["retrieval_ms"] = 0
            return state
    # 精准身份召回与语义检索并行：身份层只看名称/品牌/型号别名，
    # 不允许营销文案或配件描述决定“用户指定了什么商品”。
    from app.services.product_entity_resolver import ProductEntityResolver

    # VisualCatalogResolver already made the only allowed image→catalog decision.
    # A no-match/ambiguous image may guide category retrieval through Router, but
    # must never be reinterpreted here by the generic text entity resolver.
    visual_resolution = state.product_resolution or {}
    visual = {} if visual_resolution.get("source") == "visual_catalog" else (
        state.visual_result.model_dump() if hasattr(state.visual_result, "model_dump") else (state.visual_result or {})
    )
    identity_query = state.user_query_original or state.user_query
    # V9 单品/系列命中先锁定再检索：无需为本该跳过的泛推荐工具生成 embedding、
    # rerank 与 Filter。旧链路保留并行解析以维持原有吞吐。
    from app.core.config import USE_V9_CHUNK_RETRIEVAL
    if USE_V9_CHUNK_RETRIEVAL:
        try:
            early_resolution = await ProductEntityResolver().resolve(identity_query, visual)
        except Exception as exc:
            _log.warning("v9 product identity resolution degraded: %s", exc)
            early_resolution = None
        if early_resolution is not None:
            payload = early_resolution.payload
            # Keep an honest visual no-match/ambiguous explanation when the text
            # resolver has no stronger identity evidence.  Otherwise the later
            # generic resolver erases the image result before the client sees it.
            prior_visual_resolution = state.product_resolution if (state.product_resolution or {}).get("source") == "visual_catalog" else None
            if prior_visual_resolution and payload.get("match_type") in {"no_match", "ambiguous"}:
                payload = prior_visual_resolution
            state.product_resolution = payload
            state.retrieval_scope = payload.get("retrieval_scope", "broad")
            state.resolved_product_ids = list(payload.get("resolved_product_ids") or [])
            if payload.get("match_type") in {"exact_product", "product_family"}:
                state.retrieved_products = early_resolution.products
                state.evidence_list = early_resolution.evidence
                state.visual_matched_pids = list(state.resolved_product_ids)
                state.structured_retrieval_report = {"version": "v9", "identity_locked": True}
                state.trace_steps.append({"step_id": f"T{len(state.trace_steps) + 1:03d}",
                                          "agent_name": "Product Entity Resolver", "action": "catalog_identity_lock",
                                          "input_summary": identity_query[:80],
                                          "output_summary": f"{payload.get('match_type')}: {state.resolved_product_ids}",
                                          "latency_ms": 0, "status": "success"})
                # 唯一精确主体不再进入泛检索：普通模式与深度模式共用 dossier
                # 工具，确保规格/FAQ/评价/风险都来自一个可信单品档案。
                if payload.get("match_type") == "exact_product" and len(state.resolved_product_ids) == 1:
                    from app.workflow.react.runtime import ToolRuntime

                    state.focus_product_id = state.resolved_product_ids[0]
                    await ToolRuntime.execute_batch(state, [{
                        "id": "identity_dossier", "name": "shopping.product_dossier",
                        "args": {"product_id": state.focus_product_id, "focus": "overview"},
                    }])
                state.timing["retrieval_ms"] = round((time.perf_counter() - t0) * 1000)
                return state
            if payload.get("match_type") == "ambiguous":
                state.needs_clarification = True
                state.clarification_question = payload.get("label", "你想确认的是哪一款商品？")
                state.clarification_options = []
                state.retrieved_products, state.evidence_list = [], []
                return state
    if USE_V9_CHUNK_RETRIEVAL:
        resolver_task = asyncio.get_running_loop().create_future()
        resolver_task.set_result(early_resolution)
    else:
        resolver_task = asyncio.create_task(ProductEntityResolver().resolve(identity_query, visual))
    # 普通模式也走与 ReAct 相同的受控工具执行器：一个 shopping.search 批次，
    # 不启动 LLM loop。身份层没有锁定主体时才需要向量检索。
    if USE_V9_CHUNK_RETRIEVAL:
        from app.workflow.react.runtime import ToolRuntime

        result = await ToolRuntime.run_normal_search(state)
    else:
        result = await _retrieval.execute(state)
    try:
        resolution = await resolver_task
    except Exception as exc:  # 身份层不可用时绝不阻断泛推荐
        _log.warning("product identity resolution degraded: %s", exc)
        resolution = None

    if resolution is not None:
        payload = resolution.payload
        match_type = payload.get("match_type", "no_match")
        state.product_resolution = payload
        state.retrieval_scope = payload.get("retrieval_scope", "broad")
        state.resolved_product_ids = list(payload.get("resolved_product_ids") or [])
        # RetrievalAgent normally returns the same WorkflowState, but copy the
        # protocol fields to its returned value as well to keep that contract explicit.
        result.product_resolution = state.product_resolution
        result.retrieval_scope = state.retrieval_scope
        result.resolved_product_ids = state.resolved_product_ids
        if match_type in {"exact_product", "product_family"}:
            # 解析成功后的范围是硬边界：后续 rerank/decision/response 只能看到它。
            result.retrieved_products = resolution.products
            result.evidence_list = resolution.evidence
            state.visual_matched_pids = list(state.resolved_product_ids)
            state.trace_steps.append(
                {
                    "step_id": f"T{len(state.trace_steps) + 1:03d}",
                    "agent_name": "Product Entity Resolver",
                    "action": "catalog_identity_lock",
                    "input_summary": identity_query[:80],
                    "output_summary": f"{match_type}: {state.resolved_product_ids}",
                    "latency_ms": 0,
                    "status": "success",
                }
            )
        elif match_type == "ambiguous":
            # 不让泛检索替用户猜产品线；Response 节点只会交付澄清问题。
            result.retrieved_products = []
            result.evidence_list = []
            state.needs_clarification = True
            state.clarification_question = payload.get("label", "你想确认的是哪一款商品？")
            state.clarification_options = []
    # RAG trace: 记录 embedding 搜索结果
    try:
        from app.observability.rag_logger import RagTrace

        _rag = RagTrace(session_id=state.session_id or "", query=state.user_query)
        _rag.set_embedding(
            query_vec=[],  # 向量在检索内部，不暴露
            candidates=result.retrieved_products or [],
            latency_ms=round((time.perf_counter() - t0) * 1000),
            retrieval_mode=(result.structured_retrieval_report or {}).get("version", "legacy"),
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
            p
            for p in result.retrieved_products
            if not any(tag.lower() in (p.get("title", "") + p.get("brand", "")).lower() for tag in exclude_tags)
        ]
        filtered = before - len(result.retrieved_products)
        if filtered:
            _log.info(f"Hard-excluded {filtered} products matching exclude_tags: {exclude_tags}")

    # 检索完成后恢复原始 query（仅限 profile hints 污染，视觉信息保留给精排和回复）
    if getattr(state, "user_query_original", None):
        state.user_query = state.user_query_original
        state.user_query_original = None
    result.timing["retrieval_ms"] = round((time.perf_counter() - t0) * 1000)
    # A single-target request still owns a group.  This makes the state contract
    # identical for normal/deep and single/compound retrieval, and prevents a
    # later ReAct tool call from treating the shared list as scratch storage.
    if not result.retrieval_groups and result.retrieved_products:
        result.retrieval_groups = [{
            "group_id": "g1", "role": "推荐商品", "query": result.user_query,
            "hard_constraints": result.structured_retrieval_report or {},
            "product_ids": [p.get("product_id") for p in result.retrieved_products if p.get("product_id")],
            "evidence_product_ids": list({e.get("product_id") for e in result.evidence_list if e.get("product_id")}),
            "status": "matched", "missing_reason": "",
        }]
    return result


@register_capability("compare_retrieval")
async def _node_compare_retrieval(state: WorkflowState) -> WorkflowState:
    """对比意图多目标并行检索（Phase 4 compare 深化）。

    每个对比目标用独立子查询并行检索（避免单次混合检索稀释品牌信号），
    交替合并保证双方都进精排窗口；per-target 命中数注入 context_prompt，
    让回答基于链路验证过的有/无（而非 LLM 看不到候选就宣布没有）。
    提不出目标时回退单路 retrieval。
    """
    t0 = time.perf_counter()
    targets = ((state.plan or {}).get("meta") or {}).get("compare_targets") or []
    if not targets:
        return await _node_retrieval(state)

    cat_hint = state.constraints.sub_category or state.constraints.category or ""

    async def _retrieve_one(target: str):
        sub = state.model_copy(deep=True)  # 独立子状态，并行写入互不干扰
        sub.user_query = f"{target} {cat_hint}".strip() if cat_hint not in target else target
        sub.user_query_original = None
        sub.retrieved_products = []
        sub.evidence_list = []
        sub.trace_steps = []
        return await _node_retrieval(sub)

    results = await asyncio.gather(*[_retrieve_one(t) for t in targets], return_exceptions=True)

    # 交替合并（A1,B1,A2,B2…）+ 去重，保证每个目标的头部商品都在精排窗口内
    per_target: list[list[dict]] = []
    counts: dict[str, int] = {}
    merged_ev: list[dict] = []
    for tgt, res in zip(targets, results):
        if isinstance(res, Exception):
            _log.warning(f"compare_retrieval target failed: {tgt}: {res}")
            per_target.append([])
            counts[tgt] = 0
            continue
        # 子查询命中里只保留与目标词相关的头部（品牌/型号词命中标题才算目标命中）
        tgt_low = tgt.lower()
        tokens = [w for w in tgt_low.replace("的", " ").split() if w] or [tgt_low]
        hits = [
            p
            for p in res.retrieved_products
            if any(w in (p.get("brand", "") + p.get("title", "")).lower() for w in tokens)
        ]
        others = [p for p in res.retrieved_products if p not in hits]
        per_target.append(hits + others)
        counts[tgt] = len(hits)
        merged_ev.extend(res.evidence_list or [])

    merged: list[dict] = []
    seen: set[str] = set()
    for i in range(max((len(lst) for lst in per_target), default=0)):
        for lst in per_target:
            if i < len(lst):
                pid = lst[i].get("product_id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    merged.append(lst[i])
    state.retrieved_products = trim_for_grid(merged[:12])
    # 目标命中商品钉顶（复用精确匹配机制：reranker/decision 均会保持其在前），
    # 否则后续重排会把目标挤出生成 prompt 的候选 top-N → LLM 看不到命中商品（复测实锤）
    hit_pids = [lst[0].get("product_id", "") for lst, tgt in zip(per_target, targets) if lst and counts.get(tgt, 0) > 0]
    if hit_pids:
        state.visual_matched_pids = list(dict.fromkeys((state.visual_matched_pids or []) + [p for p in hit_pids if p]))
        for p in state.retrieved_products:
            if p.get("product_id") in hit_pids:
                p["reranker_score"] = max(p.get("reranker_score", 0), 0.95)
    kept = {p.get("product_id") for p in state.retrieved_products}
    ev_seen: set[tuple] = set()
    state.evidence_list = []
    for e in merged_ev:
        key = (e.get("product_id", ""), str(e.get("text", e.get("content", "")))[:60])
        if e.get("product_id") in kept and key not in ev_seen:
            ev_seen.add(key)
            state.evidence_list.append(e)

    # 链路验证过的 per-target 命中数 → 注入 Response 的上下文提示
    lines = []
    for tgt in targets:
        n = counts.get(tgt, 0)
        lines.append(f"- 「{tgt}」库内命中 {n} 件" + ("（未找到，请明确告知用户无法对比此目标）" if n == 0 else ""))
    state.context_prompt = (state.context_prompt or "") + "\n[对比检索结果（已逐目标验证）]\n" + "\n".join(lines)

    from app.framework.blackboard import current_board as _cb

    bb = _cb()
    if bb is not None:
        await bb.publish("compare.targets_retrieved", {"counts": counts}, producer="compare_retrieval")

    state.trace_steps.append(
        {
            "step_id": f"T{len(state.trace_steps) + 1:03d}",
            "agent_name": "Compare Retrieval (multi-target)",
            "action": "parallel_target_retrieval",
            "input_summary": f"targets={targets}",
            "output_summary": f"counts={counts}, merged={len(state.retrieved_products)}",
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "status": "success" if any(counts.values()) else "fallback",
        }
    )
    state.timing["compare_retrieval_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


@register_capability("multi_query_retrieval")
async def _node_multi_query_retrieval(state: WorkflowState) -> WorkflowState:
    """QU V2 多目标并行检索（compare_retrieval 的泛化）。

    消费 Router 拆分的 retrieval_plan.sub_queries（如 bundle 场景的 上衣/裤子/鞋 三路）：
    每路独立子查询并行检索→打 group_role 标记→交替合并去重→每组 top1 钉顶，
    命中统计注入 context_prompt 让回答分组说明（缺货组诚实声明）。无 sub_queries 退化单路。
    """
    t0 = time.perf_counter()
    sub_queries = state.retrieval_plan.sub_queries or []
    if len(sub_queries) < 2:
        return await _node_retrieval(state)

    # V9 将所有 Router 独立目标收进同一受控 shopping.search 批次：每个调用在
    # 隔离快照内执行，再由 ToolRuntime 按 Router 顺序归并。不要再为每个目标启动
    # 一条嵌套工作流，否则工具账本、去重策略和预算都会脱离主请求。
    from app.core.config import USE_V9_CHUNK_RETRIEVAL
    if USE_V9_CHUNK_RETRIEVAL:
        from app.workflow.react.runtime import ToolRuntime

        await ToolRuntime.run_normal_search(state)
        by_pid = {str(p.get("product_id") or ""): p for p in (state.retrieved_products or [])}
        groups_by_id = {
            str(g.get("group_id") if isinstance(g, dict) else g.group_id): g
            for g in (state.retrieval_groups or [])
        }
        per_group: list[list[dict]] = []
        counts: dict[str, int] = {}
        for index, sq in enumerate(sub_queries, 1):
            role = sq.role or sq.query
            group = groups_by_id.get(f"plan:{index}")
            product_ids = (group.get("product_ids") if isinstance(group, dict) else getattr(group, "product_ids", [])) or []
            products = [dict(by_pid[pid]) for pid in product_ids if pid in by_pid]
            for product in products:
                product["group_role"] = role
            per_group.append(products)
            counts[role] = len(products)

        merged: list[dict] = []
        seen: set[str] = set()
        for offset in range(max((len(items) for items in per_group), default=0)):
            for items in per_group:
                if offset < len(items):
                    pid = str(items[offset].get("product_id") or "")
                    if pid and pid not in seen:
                        seen.add(pid)
                        merged.append(items[offset])
        state.retrieved_products = trim_for_grid(merged[:12])
        top_pids = [items[0].get("product_id", "") for items in per_group if items]
        if top_pids:
            state.visual_matched_pids = list(dict.fromkeys((state.visual_matched_pids or []) + top_pids))
            for product in state.retrieved_products:
                if product.get("product_id") in top_pids:
                    product["reranker_score"] = max(product.get("reranker_score", 0), 0.95)
        kept = {p.get("product_id") for p in state.retrieved_products}
        state.evidence_list = [e for e in (state.evidence_list or []) if e.get("product_id") in kept]
        missing = [role for role, count in counts.items() if count == 0]
        stat = " ".join(f"{role}:{count}件" for role, count in counts.items())
        miss_note = ("；" + "、".join(f"「{role}」未找到符合条件的商品" for role in missing) + "，回答时须如实说明") if missing else ""
        state.context_prompt = (state.context_prompt or "") + f"\n[分组检索] {stat}{miss_note}"
        state.trace_steps.append({
            "step_id": f"T{len(state.trace_steps) + 1:03d}",
            "agent_name": "Multi-Query Retrieval (tool batch)",
            "action": "parallel_group_retrieval",
            "input_summary": f"groups={[sq.role or sq.query for sq in sub_queries]}",
            "output_summary": f"counts={counts}, merged={len(state.retrieved_products)}",
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "status": "success" if any(counts.values()) else "fallback",
        })
        state.timing["multi_query_retrieval_ms"] = round((time.perf_counter() - t0) * 1000)
        return state

    async def _retrieve_group(sq):
        sub = state.model_copy(deep=True)
        sub.user_query = sq.query
        sub.user_query_original = None
        sub.retrieved_products = []
        sub.evidence_list = []
        sub.trace_steps = []
        if sq.category:
            sub.constraints.category = sq.category
            sub.retrieval_plan.category = sq.category
        if sq.budget_hint:
            sub.constraints.budget_max = sq.budget_hint
        # 子目标的 Router 约束必须和 query 一起进入 V9 工具签名；否则多目标会
        # 错误共享主目标的偏好/避雷条件。
        sub.retrieval_plan.entity_terms = list(sq.entity_terms or [])
        sub.retrieval_plan.must_constraints = list(sq.must_constraints or [])
        sub.retrieval_plan.soft_preferences = list(sq.soft_preferences or [])
        sub.retrieval_plan.avoid_constraints = list(sq.avoid_constraints or [])
        sub.retrieval_plan.evidence_focus = list(sq.evidence_focus or [])
        sub.retrieval_plan.answer_goal = sq.answer_goal or sub.retrieval_plan.answer_goal
        sub.retrieval_plan.ambiguity = sq.ambiguity or sub.retrieval_plan.ambiguity
        sub.retrieval_plan.sub_queries = []  # 子路不再递归拆分
        sub.retrieval_plan.top_k = max(4, state.retrieval_plan.top_k // len(sub_queries))
        return await _node_retrieval(sub)

    results = await asyncio.gather(*[_retrieve_group(sq) for sq in sub_queries], return_exceptions=True)

    per_group: list[list[dict]] = []
    counts: dict[str, int] = {}
    merged_ev: list[dict] = []
    group_records = []
    candidate_groups, candidate_trace, evidence_packs = [], [], {}
    for sq, res in zip(sub_queries, results):
        role = sq.role or sq.query
        if isinstance(res, Exception):
            _log.warning(f"multi_query group failed: {role}: {res}")
            per_group.append([])
            counts[role] = 0
            group_records.append({"group_id": f"g{len(group_records) + 1}", "role": role,
                                  "query": sq.query, "status": "failed", "missing_reason": "检索暂时失败"})
            continue
        prods = res.retrieved_products or []
        for p in prods:
            p["group_role"] = role  # 分组标记（前端分组卡/分组回答依据）
        per_group.append(prods)
        counts[role] = len(prods)
        merged_ev.extend(res.evidence_list or [])
        candidate_groups.extend(getattr(res, "candidate_groups", []) or [])
        candidate_trace.extend(getattr(res, "candidate_trace", []) or [])
        evidence_packs.update(getattr(res, "evidence_packs", {}) or {})
        report = getattr(res, "structured_retrieval_report", {}) or {}
        group_records.append({
            "group_id": f"g{len(group_records) + 1}", "role": role, "query": sq.query,
            "hard_constraints": report, "product_ids": [p.get("product_id") for p in prods if p.get("product_id")],
            "evidence_product_ids": list({e.get("product_id") for e in (res.evidence_list or []) if e.get("product_id")}),
            "status": "matched" if prods else "missing",
            "missing_reason": "未找到同时满足当前条件的商品" if not prods else "",
        })

    merged: list[dict] = []
    seen: set[str] = set()
    for i in range(max((len(lst) for lst in per_group), default=0)):
        for lst in per_group:
            if i < len(lst):
                pid = lst[i].get("product_id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    merged.append(lst[i])
    state.retrieved_products = trim_for_grid(merged[:12])
    state.retrieval_groups = group_records
    state.candidate_groups = candidate_groups
    state.candidate_trace = candidate_trace
    state.evidence_packs = evidence_packs
    # 每组 top1 钉顶（复用 compare 修复机制，防全局重排把某一组挤出生成 prompt 窗口）
    top_pids = [lst[0].get("product_id", "") for lst in per_group if lst]
    if top_pids:
        state.visual_matched_pids = list(dict.fromkeys((state.visual_matched_pids or []) + [p for p in top_pids if p]))
        for p in state.retrieved_products:
            if p.get("product_id") in top_pids:
                p["reranker_score"] = max(p.get("reranker_score", 0), 0.95)
    kept = {p.get("product_id") for p in state.retrieved_products}
    ev_seen: set[tuple] = set()
    state.evidence_list = []
    for e in merged_ev:
        key = (e.get("product_id", ""), str(e.get("text", e.get("content", "")))[:60])
        if e.get("product_id") in kept and key not in ev_seen:
            ev_seen.add(key)
            state.evidence_list.append(e)

    # 分组命中统计 → Response 分组回答依据（缺货组必须如实说明）
    stat = " ".join(f"{r}:{n}件" for r, n in counts.items())
    missing = [r for r, n in counts.items() if n == 0]
    miss_note = (
        ("；" + "、".join(f"「{r}」未找到符合条件的商品" for r in missing) + "，回答时须如实说明") if missing else ""
    )
    state.context_prompt = (state.context_prompt or "") + f"\n[分组检索] {stat}{miss_note}"

    from app.framework.blackboard import current_board as _cb2

    bb = _cb2()
    if bb is not None:
        await bb.publish("multi_query.groups_retrieved", {"counts": counts}, producer="multi_query_retrieval")

    state.trace_steps.append(
        {
            "step_id": f"T{len(state.trace_steps) + 1:03d}",
            "agent_name": "Multi-Query Retrieval (grouped)",
            "action": "parallel_group_retrieval",
            "input_summary": f"groups={[sq.role or sq.query for sq in sub_queries]}",
            "output_summary": f"counts={counts}, merged={len(state.retrieved_products)}",
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "status": "success" if any(counts.values()) else "fallback",
        }
    )
    state.timing["multi_query_retrieval_ms"] = round((time.perf_counter() - t0) * 1000)
    return state


@register_capability("reranker")
async def _node_reranker(state: WorkflowState) -> WorkflowState:
    """Qwen Reranker 精排：对语义检索结果进行语义重排序"""
    t0 = time.perf_counter()
    products = state.retrieved_products
    if (state.structured_retrieval_report or {}).get("version") == "v9":
        # V9 的 shopping.search 已完成 Top24→Top12 本地 BGE 精排。再次精排不仅
        # 浪费一次本地模型，还会打乱 LLM Filter 已确认的主选/备选顺序。
        state.timing["rerank_ms"] = 0
        return state
    # lite 档：跳过 Reranker LLM 调用（P2-1：state.mode 替代 [FAST_MODE] 字符串嵌 prompt）
    if state.mode == "lite":
        state.timing["rerank_ms"] = 0
        return state
    if len(products) <= 1:
        state.timing["rerank_ms"] = 0
        return state

    try:
        # 精排逻辑已收敛到 RerankFusion（LLM 精排 + 校准 + 视觉置顶钩子）
        # 候选门控：只精排前 8 个（本地 reranker 每 doc ~百毫秒级），尾部保留召回序拼接
        _head, _tail = products[:8], products[8:]
        _ranked_head = await _reranker.rerank(
            query=state.user_query,
            products=_head,
            evidence=state.evidence_list,
            visual_matched_pids=state.visual_matched_pids,
        )
        state.retrieved_products = _ranked_head + _tail

        # 记录 trace
        step_num = len(state.trace_steps) + 1
        top3 = [f"{p.get('reranker_score', 0):.3f}" for p in state.retrieved_products[:3]]
        state.trace_steps.append(
            {
                "step_id": f"T{step_num:03d}",
                "agent_name": "Qwen Reranker",
                "action": "semantic_rerank",
                "input_summary": f"{len(products)} candidates",
                "output_summary": f"reranked, top3 scores: {top3}",
                "latency_ms": 0,
                "status": "success",
            }
        )
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


@register_capability("decision")
async def _node_decision(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    # Phase 3 A2A：动态模式下等待 Router 后台召回的长期偏好（与检索/精排已并行）；
    # 超时降级空，评分不受阻塞。
    from app.framework.blackboard import current_board as _cb

    _bb = _cb()
    if _bb is not None and not state.used_memories:
        _art = await _bb.wait_for("memories.ready", timeout=_MEMORY_RECALL_TIMEOUT_SECONDS)
        if _art:
            state.used_memories = _art.content.get("memories", []) or []
    state = await _decision.execute(state)
    # 按 final_score 排序，但视觉精确匹配商品始终排在最前
    if state.decision_results and state.retrieved_products and (state.structured_retrieval_report or {}).get("version") != "v9":
        ranked = {r["product_id"]: i for i, r in enumerate(state.decision_results)}
        visual_pids = set(state.visual_matched_pids or [])
        state.retrieved_products.sort(
            key=lambda p: (
                0 if p.get("product_id") in visual_pids else 1,  # 精确匹配优先
                ranked.get(p.get("product_id", ""), 999),  # 同组内按分数排
            )
        )
        state.evidence_list.sort(key=lambda e: ranked.get(e.get("product_id", ""), 999))
    # Final response (both /v2 and SSE) only reads RecommendationBrief.  Build
    # it immediately after Decision so the non-stream graph cannot accidentally
    # feed a response model an empty primary-product scope.
    from app.services.recommendation_brief import build_recommendation_brief

    build_recommendation_brief(state)
    # Memory Lite: 结构化商品列表存入 context_snapshot (供 FollowUpEngine 指代解析)
    if state.conversation_id and state.retrieved_products:
        try:
            structured = []
            for p in state.retrieved_products[:10]:
                pid = p.get("product_id", "")
                if pid:
                    structured.append(
                        {
                            "product_id": pid,
                            "title": p.get("title", "")[:60],
                            "brand": p.get("brand", ""),
                            "price": p.get("price", 0),
                        }
                    )
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


@register_capability("response")
async def _node_response(state: WorkflowState) -> WorkflowState:
    t0 = time.perf_counter()
    result = await _response.execute(state)
    result.timing["response_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


@register_capability("evidence_check")
def _node_evidence_check(state: WorkflowState) -> WorkflowState:
    """证据充足性检查：在 Reranker 之后、Decision 之前执行。"""
    t0 = time.perf_counter()
    state.sufficiency_report = _evidence_checker.check(state)
    step_num = len(state.trace_steps) + 1
    state.trace_steps.append(
        {
            "step_id": f"T{step_num:03d}",
            "agent_name": "Evidence Sufficiency Checker",
            "action": "evidence_check",
            "input_summary": f"{state.sufficiency_report.get('total_evidence', 0)} evidence items",
            "output_summary": "sufficient"
            if state.sufficiency_report.get("sufficient")
            else f"missing: {state.sufficiency_report.get('missing_types', [])}",
            "latency_ms": 0,
            "status": "pass" if state.sufficiency_report.get("sufficient") else "insufficient",
        }
    )
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


@register_route("router_next")
def _router_next(state: WorkflowState) -> str:
    """Router 后决定下一节点：有图优先视觉解析，闲聊且无图→直接回复，否则→检索"""
    if state.image_url:
        return "visual"
    if state.intent == "chitchat":
        return "response"
    return "retrieval"


@register_route("has_results")
def _has_results(state: WorkflowState) -> str:
    return "decision" if state.retrieved_products else "response"


# ================================================================
# Phase 4+5: 动态编排（Planner / Supervisor 执行器 / Reflect 自纠错）
# ================================================================


async def _node_planner(state: WorkflowState) -> WorkflowState:
    """Plan-and-Execute 第一段：按 intent 生成 ExecutionPlan（本期规则模板，0 LLM 调用）。"""
    t0 = time.perf_counter()
    from app.framework.orchestration import get_planner

    plan = await get_planner().plan(state)
    state.plan = plan.model_dump()
    elapsed = round((time.perf_counter() - t0) * 1000)
    _pname = "Planner (llm)" if plan.meta.get("planner") == "llm" else "Planner (rule)"
    _trigger = f", trigger={plan.meta['trigger']}" if plan.meta.get("trigger") else ""
    state.trace_steps.append(
        {
            "step_id": f"T{len(state.trace_steps) + 1:03d}",
            "agent_name": _pname,
            "action": "plan_generation",
            "input_summary": f"intent={state.intent}, image={bool(state.image_url)}{_trigger}",
            "output_summary": f"steps={[s.capability for s in plan.steps]} | {plan.rationale}",
            "latency_ms": elapsed,
            "status": "success",
        }
    )
    state.timing["plan_ms"] = elapsed
    return state


async def _dispatch_capability(step, state: WorkflowState) -> WorkflowState:
    """派发单个计划步骤：内置节点能力 / tool:<name> 工具 / 未知能力降级跳过。"""
    cap = step.capability

    # 真流式模式（P0-2）：response 步交由 SSE 层 generate_stream 边生成边推，
    # 这里只记 completed；compare 命中提示/工具步回填都在 context_prompt 中被其消费
    if cap == "response" and (state.plan or {}).get("stream_response"):
        state.trace_steps.append(
            {
                "step_id": f"T{len(state.trace_steps) + 1:03d}",
                "agent_name": "Supervisor",
                "action": "dispatch",
                "input_summary": cap,
                "output_summary": "deferred to SSE stream",
                "latency_ms": 0,
                "status": "skipped",
            }
        )
        return state

    # 短路：无检索结果时跳过 decision（对齐 legacy has_results 语义；response 自带空结果模板）
    if cap == "decision" and not state.retrieved_products:
        state.trace_steps.append(
            {
                "step_id": f"T{len(state.trace_steps) + 1:03d}",
                "agent_name": "Supervisor",
                "action": "dispatch",
                "input_summary": cap,
                "output_summary": "skipped: no retrieved products",
                "latency_ms": 0,
                "status": "skipped",
            }
        )
        return state

    if cap.startswith("tool:"):
        tool_name = cap[len("tool:") :]
        from app.framework.tools import ToolContext
        from app.providers.tools import get_tool_registry

        ctx = ToolContext(
            user_id=state.user_id,
            session_id=state.session_id,
            conversation_id=state.conversation_id,
            args_raw=state.user_query,
            state=state,
        )
        res = await get_tool_registry().invoke(tool_name, {}, ctx)  # trace 自动进 skill_executions
        # Phase 6-B2：工具步结果回填上下文，供后续 response 步骤合成回答
        if res.message:
            state.context_prompt = (state.context_prompt or "") + f"\n[工具 {tool_name} 结果]\n{res.message[:400]}"
        return state

    fn = get_capability(cap)
    if fn is None:
        _log.warning(f"unknown capability in plan: {cap}")
        state.trace_steps.append(
            {
                "step_id": f"T{len(state.trace_steps) + 1:03d}",
                "agent_name": "Supervisor",
                "action": "dispatch",
                "input_summary": cap,
                "output_summary": "skipped: unknown capability",
                "latency_ms": 0,
                "status": "skipped",
            }
        )
        return state

    result = fn(state)
    if asyncio.iscoroutine(result):
        result = await result
    return result if result is not None else state


async def _node_supervisor(state: WorkflowState) -> WorkflowState:
    """Plan-and-Execute 第二段：循环派发就绪步骤；同 parallel_group 用 gather 并发。"""
    from app.framework.orchestration import ExecutionPlan

    plan = ExecutionPlan(**(state.plan or {}))
    from app.framework.blackboard import current_board as _cb

    bb = _cb()
    batches = 0
    while True:
        batches += 1
        if batches > MAX_SUPERVISOR_STEPS:
            _log.warning("supervisor batch guard tripped, aborting plan")
            break
        ready = plan.next_ready(set(state.completed_steps))
        if not ready:
            break
        if len(ready) == 1:
            state = await _dispatch_capability(ready[0], state)
            state.completed_steps.append(ready[0].step_id)
        else:
            t0 = time.perf_counter()
            # 并行组：共享同一 state（asyncio 单线程，追加安全；写字段互不冲突由 Planner 保证）
            await asyncio.gather(*[_dispatch_capability(s, state) for s in ready])
            group = ready[0].parallel_group or "pg"
            state.timing[f"parallel_{group}_ms"] = round((time.perf_counter() - t0) * 1000)
            for s in ready:
                state.completed_steps.append(s.step_id)
        # Phase 3 A2A：每步完成发布 <capability>.done 事件（供未来跨 Agent 订阅消费）
        if bb is not None:
            for s in ready:
                await bb.publish(f"{s.capability}.done", {"step_id": s.step_id}, producer="supervisor")
    return state


def _requeue(state: WorkflowState, capabilities: list) -> None:
    """Reflect 回环：向计划尾部追加新步骤（step_id 带 reflect 轮次前缀，保证唯一）。"""
    steps = list(state.plan.get("steps", []))
    base = len(steps) + 1
    prev: list = []
    for i, cap in enumerate(capabilities):
        sid = f"r{state.reflect_count}_{base + i}_{cap.replace('tool:', 'tool_')}"
        steps.append(
            {"step_id": sid, "capability": cap, "depends_on": list(prev), "parallel_group": None, "optional": False}
        )
        prev = [sid]
    state.plan["steps"] = steps


async def _node_reflect(state: WorkflowState) -> WorkflowState:
    """Reflexion 节点：Guard 评估 + 自纠错决策（取代动态模式下的 guard 节点）。

    决策写入 state.plan["reflect_route"]，供纯函数路由 reflect_next 读取：
    - 硬失败（幻觉/无货编造）→ 清空 answer + 纠正指令 → 重排 response；
    - 零结果（非闲聊，仅首轮）→ top_k+5 → 重排检索链；
    - 预算耗尽/通过 → end。
    """
    t0 = time.perf_counter()
    _guard.check(state)  # 填 harness_report（与 legacy guard 输出字段一致）
    passed = state.harness_report.get("passed", True)
    state.harness_report["failure_source"] = None if passed else "response_guard"

    from app.core.config import REFLECT_MAX_RETRIES

    max_reflects = int((state.plan or {}).get("max_reflects", REFLECT_MAX_RETRIES))
    route = "end"
    reason = "passed" if passed else "budget_exhausted"
    if state.reflect_count < max_reflects:
        if not passed:
            state.reflect_count += 1
            state.context_prompt = (
                state.context_prompt or ""
            ) + "\n[纠正] 只能引用候选列表内的商品/品牌/价格，禁止编造"
            state.answer = ""
            _requeue(state, ["response"])
            route, reason = "supervisor", "guard_failed -> regenerate"
        elif not state.retrieved_products and state.intent != "chitchat" and state.reflect_count == 0:
            state.reflect_count += 1
            state.retrieval_plan.top_k += 5
            _requeue(state, ["retrieval", "reranker", "evidence_check", "decision", "response"])
            route, reason = "supervisor", "zero_results -> widen retrieval"
    state.plan["reflect_route"] = route

    # Phase 3 A2A：请求结束时落黑板汇总（timing 计数 + trace 可见）
    from app.framework.blackboard import current_board as _cb

    bb = _cb()
    if bb is not None and route == "end":
        state.timing["a2a_events"] = len(bb.history)
        state.trace_steps.append(
            {
                "step_id": f"T{len(state.trace_steps) + 1:03d}",
                "agent_name": "Blackboard (A2A)",
                "action": "a2a_summary",
                "input_summary": f"{len(bb.history)} artifacts",
                "output_summary": f"topics={bb.topics()}",
                "latency_ms": 0,
                "status": "success",
            }
        )

    elapsed = round((time.perf_counter() - t0) * 1000)
    state.trace_steps.append(
        {
            "step_id": f"T{len(state.trace_steps) + 1:03d}",
            "agent_name": "Reflect",
            "action": "self_check",
            "input_summary": f"passed={passed}, products={len(state.retrieved_products)}",
            "output_summary": f"route={route} ({reason}), reflect_count={state.reflect_count}",
            "latency_ms": elapsed,
            "status": "success" if passed else "fallback",
        }
    )
    state.timing["reflect_ms"] = state.timing.get("reflect_ms", 0) + elapsed
    return state


@register_route("reflect_next")
def _reflect_next(state: WorkflowState) -> str:
    """纯函数路由：读 reflect 节点写入的决策。"""
    return (state.plan or {}).get("reflect_route", "end")


def _traced(name: str, fn):
    """节点观测统一包裹（P1-3，对齐 amap 观测套壳的单服务版）。

    不用 monkey-patch add_node（那是多服务+第三方节点全覆盖的方案，代价是上游私有 API
    耦合），构图处显式包裹：
    - timing 兜底：节点未自写 ``{name}_ms`` 时补齐（已写则不覆盖，零行为变更）；
    - 异常兜底：记失败 trace 后 re-raise（观测失败不吞业务异常）；
    - 兼容 sync/async 节点；观测自身异常独立容错（观测不能杀死业务）。
    """
    if getattr(fn, "_observability_wrapped", False):  # 防重包装（多张图复用同一节点）
        return fn

    async def wrapper(state: WorkflowState) -> WorkflowState:
        t0 = time.perf_counter()
        try:
            result = fn(state)
            out = await result if asyncio.iscoroutine(result) else result
        except Exception:
            try:
                state.trace_steps.append(
                    {
                        "step_id": f"T{len(state.trace_steps) + 1:03d}",
                        "agent_name": name,
                        "action": "node",
                        "input_summary": (state.user_query or "")[:40],
                        "output_summary": "exception",
                        "latency_ms": round((time.perf_counter() - t0) * 1000),
                        "status": "failed",
                    }
                )
                state.timing.setdefault(f"{name}_ms", round((time.perf_counter() - t0) * 1000))
            except Exception:  # noqa: BLE001 — 观测失败绝不覆盖业务异常
                pass
            raise
        try:
            out.timing.setdefault(f"{name}_ms", round((time.perf_counter() - t0) * 1000))
        except Exception:  # noqa: BLE001
            pass
        return out

    wrapper._observability_wrapped = True
    wrapper.__name__ = f"traced_{name}"
    return wrapper


def build_workflow() -> StateGraph:
    workflow = StateGraph(WorkflowState)

    workflow.add_node("router", _traced("router", _node_router))
    workflow.add_node("visual", _traced("visual", _node_visual))
    workflow.add_node("retrieval", _traced("retrieval", _node_retrieval))
    workflow.add_node("reranker", _traced("reranker", _node_reranker))
    workflow.add_node("evidence_check", _traced("evidence_check", _node_evidence_check))
    workflow.add_node("decision", _traced("decision", _node_decision))
    workflow.add_node("response", _traced("response", _node_response))
    workflow.add_node("guard", _traced("guard", _node_guard))

    workflow.set_entry_point("visual")
    workflow.add_edge("visual", "router")
    workflow.add_conditional_edges(
        "router", get_route("router_next"), {"visual": "retrieval", "retrieval": "retrieval", "response": "response"}
    )
    workflow.add_edge("retrieval", "reranker")
    workflow.add_edge("reranker", "evidence_check")
    workflow.add_conditional_edges(
        "evidence_check", get_route("has_results"), {"decision": "decision", "response": "response"}
    )
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
    """无 response/guard 节点的 workflow — 供 SSE 真流式路径使用。

    注意不能在 build_workflow() 上追加 decision→END 边（LangGraph 会 fan-out，
    response 仍会执行），必须重建一张不含 response/guard 的图；
    回答生成由 SSE 层调 ResponseAgent.generate_stream 真流式输出。
    """
    global _compiled_no_response
    if _compiled_no_response is None:
        wf = StateGraph(WorkflowState)
        wf.add_node("router", _traced("router", _node_router))
        wf.add_node("visual", _traced("visual", _node_visual))
        wf.add_node("retrieval", _traced("retrieval", _node_retrieval))
        wf.add_node("reranker", _traced("reranker", _node_reranker))
        wf.add_node("evidence_check", _traced("evidence_check", _node_evidence_check))
        wf.add_node("decision", _traced("decision", _node_decision))
        wf.set_entry_point("visual")
        wf.add_edge("visual", "router")
        wf.add_conditional_edges(
            "router", get_route("router_next"), {"visual": "retrieval", "retrieval": "retrieval", "response": END}
        )
        wf.add_edge("retrieval", "reranker")
        wf.add_edge("reranker", "evidence_check")
        wf.add_conditional_edges("evidence_check", get_route("has_results"), {"decision": "decision", "response": END})
        wf.add_edge("decision", END)
        _compiled_no_response = wf.compile()
    return _compiled_no_response


def build_dynamic_workflow() -> StateGraph:
    """Phase 4+5 动态图：router -> planner -> supervisor -> reflect -> (supervisor | END)。

    legacy build_workflow 保持不变；由 ENABLE_DYNAMIC_ORCHESTRATION 切换（config.py 里默认 True）。
    """
    wf = StateGraph(WorkflowState)
    wf.add_node("visual", _traced("visual", _node_visual))
    wf.add_node("router", _traced("router", _node_router))
    wf.add_node("planner", _traced("planner", _node_planner))
    wf.add_node("supervisor", _traced("supervisor", _node_supervisor))
    wf.add_node("reflect", _traced("reflect", _node_reflect))
    wf.set_entry_point("visual")
    wf.add_edge("visual", "router")
    wf.add_edge("router", "planner")
    wf.add_edge("planner", "supervisor")
    wf.add_edge("supervisor", "reflect")
    wf.add_conditional_edges("reflect", get_route("reflect_next"), {"supervisor": "supervisor", "end": END})
    return wf


_compiled_dynamic = None


def get_dynamic_workflow():
    global _compiled_dynamic
    if _compiled_dynamic is None:
        _compiled_dynamic = build_dynamic_workflow().compile()
    return _compiled_dynamic


async def _node_planner_stream(state: WorkflowState) -> WorkflowState:
    """真流式变体 planner：标记 response 步延迟到 SSE 层生成。"""
    state = await _node_planner(state)
    state.plan["stream_response"] = True
    return state


def build_dynamic_workflow_no_response() -> StateGraph:
    """P0-2：真流式主链的动态图变体（router -> planner_stream -> supervisor -> END）。

    已知限制：无 reflect 回环——答案由 SSE 层边生成边推送无法撤回，
    guard 由 SSE 层流完后补跑（agent_stream 真流式段）；重生成式纠错另立课题。
    """
    wf = StateGraph(WorkflowState)
    wf.add_node("visual", _traced("visual", _node_visual))
    wf.add_node("router", _traced("router", _node_router))
    wf.add_node("planner", _traced("planner", _node_planner_stream))
    wf.add_node("supervisor", _traced("supervisor", _node_supervisor))
    wf.set_entry_point("visual")
    wf.add_edge("visual", "router")
    wf.add_edge("router", "planner")
    wf.add_edge("planner", "supervisor")
    wf.add_edge("supervisor", END)
    return wf


_compiled_dynamic_no_response = None


def get_dynamic_workflow_no_response():
    global _compiled_dynamic_no_response
    if _compiled_dynamic_no_response is None:
        _compiled_dynamic_no_response = build_dynamic_workflow_no_response().compile()
    return _compiled_dynamic_no_response


async def run_workflow(
    user_query: str,
    image_url: str | None = None,
    session_id: str = "",
    user_id: str = "",
    conversation_id: str = "",
    enable_checkpoint: bool = True,
    prefill_state: WorkflowState | None = None,
    context_prompt: str = "",
    no_response: bool = False,
    fast_mode: bool = False,
    use_cache: bool = True,
    mode: str = "",
) -> WorkflowState:
    # P2-1 三档派发：mode 显式优先；fast_mode 旧参数映射 lite（兼容存量调用方）
    resolved_mode = mode or ("lite" if fast_mode else "standard")
    if no_response:
        # P0-2：真流式主链同样按 flag 选动态图（否则动态编排/LLM Planner/compare_retrieval 在主路径全部失效）
        from app.core.config import ENABLE_DYNAMIC_ORCHESTRATION as _dyn_nr

        # mode=max 作为动态编排的按请求灰度入口（比全局 flag 更细粒度）
        wf = get_dynamic_workflow_no_response() if (_dyn_nr or resolved_mode == "max") else get_workflow_no_response()
    else:
        from app.core.config import ENABLE_DYNAMIC_ORCHESTRATION

        wf = get_dynamic_workflow() if (ENABLE_DYNAMIC_ORCHESTRATION or resolved_mode == "max") else get_workflow()

    # 全链路 trace：为本次请求设置共享 trace_id（session_id 作为关联键），
    # 使 Router/Retrieval/Reranker/Decision/Response 的 LLM span 串成一条链路。
    from app.observability.request_context import ensure_trace_id

    ensure_trace_id(session_id)

    # ---- Workflow 级缓存（与 checkpoint 解耦）：相同 query + image 在 TTL 内直接返回 ----
    # key 含 context_prompt 摘要：同 query 不同会话上下文（追问/偏好）不串结果；
    # 含 mode：lite/standard/max 不同档链路结果不互串
    cache_key = make_key(
        "workflow", user_query, image_url or "noimg", user_id, session_id, resolved_mode, (context_prompt or "")[:120]
    )
    if not use_cache:
        state = await _run_uncached(
            user_query,
            image_url,
            session_id,
            user_id,
            conversation_id,
            wf,
            enable_checkpoint,
            prefill_state,
            context_prompt,
            resolved_mode,
        )
    else:

        async def _do_run():
            return await _run_uncached(
                user_query,
                image_url,
                session_id,
                user_id,
                conversation_id,
                wf,
                enable_checkpoint,
                prefill_state,
                context_prompt,
                resolved_mode,
            )

        state = await cached(
            cache_key,
            REDIS_CACHE_TTL_WORKFLOW,
            _do_run,
            serializer=lambda v: json.dumps(v.model_dump(), ensure_ascii=False, default=str),
            deserializer=lambda s: WorkflowState(**json.loads(s)),
        )

    # cached() may return dict on cache hit; ensure WorkflowState
    if isinstance(state, dict):
        state = WorkflowState(**state)

    return state


async def _run_uncached(
    user_query: str,
    image_url: str | None,
    session_id: str,
    user_id: str,
    conversation_id: str,
    wf,
    enable_checkpoint: bool,
    prefill_state: WorkflowState | None = None,
    context_prompt: str = "",
    mode: str = "standard",
) -> WorkflowState:
    # P2-1：mode 显式字段替代 "[FAST_MODE]" 嵌 prompt 的 magic string
    if prefill_state is not None:
        state = prefill_state
        # Prefills carry constraints or a trusted product scope, not request
        # identity. Preserve the caller's authenticated/session context so the
        # resulting state remains usable by memory, observability and SSE.
        state.session_id = session_id or state.session_id
        state.user_id = user_id or state.user_id
        state.conversation_id = conversation_id or state.conversation_id
        state.user_query = user_query
        state.image_url = image_url
        state.context_prompt = context_prompt
        state.mode = mode
    else:
        state = WorkflowState(
            session_id=session_id or "",
            user_id=user_id,
            conversation_id=conversation_id,
            user_query=user_query,
            image_url=image_url,
            context_prompt=context_prompt,
            mode=mode,
        )

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
    # Phase 3 A2A：动态编排模式下绑请求级黑板（ContextVar，节点子任务继承可见；
    # 不挂 state：LangGraph 节点边界重建 Pydantic state 会丢失动态私有属性）
    from app.core.config import ENABLE_DYNAMIC_ORCHESTRATION as _dyn

    _bb_token = None
    if _dyn:
        from app.framework.blackboard import Blackboard, set_current_board

        _bb_token = set_current_board(Blackboard())
    try:
        result_dict = await wf.ainvoke(state)
    finally:
        if _bb_token is not None:
            from app.framework.blackboard import reset_current_board

            reset_current_board(_bb_token)
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
