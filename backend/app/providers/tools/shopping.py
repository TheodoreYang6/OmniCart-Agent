"""购物核心工具族 —— 只读检索 / 详情 / 对比。

Phase 1 仅注册 + 单测，暂不接入实时 SSE 路径（供后续 Planner 动态调用）。
包装现有 ``product_repo`` 能力，不引入新依赖。
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from app.framework.tools.protocols import Tool, ToolContext, ToolResult, ToolSpec
from app.services.category_normalization import CANONICAL_CATEGORIES, normalize_category

logger = logging.getLogger(__name__)

__all__ = [
    "SearchProductsTool", "GetProductDetailTool", "ProductDossierTool",
    "CompareProductsTool", "CheckInventoryTool", "build_product_dossier",
]


def _normalize_category(category: str | None) -> str | None:
    """兼容旧导入路径；真实实现供检索与决策节点共用。"""
    return normalize_category(category)


def _avg_rating(product) -> tuple[float, int]:
    reviews = product.rag_knowledge.user_reviews if product.rag_knowledge else []
    ratings = [r.rating for r in reviews]
    avg = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
    return avg, len(ratings)


class SearchProductsTool(Tool):
    spec = ToolSpec(
        name="shopping.search", category="shopping", permission="read",
        timeout_ms=60_000,
        description=(
            "深度检索商品：语义召回+精排+证据检查+决策评分的完整管线。"
            "需要了解/推荐/比价商品时调用；可多次调用；对比多个目标时请分别检索每个目标"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description":
                          "检索词：只放商品属性词干（品类+关键属性，如'干皮 保湿面霜'）。"
                          "去掉口语前缀；预算/口碑/品类等有专门参数的约束不要写进 query，"
                          "否则会污染语义召回与关键词匹配"},
                "category": {"type": "string", "description":
                             "一级品类；仅可使用给定枚举，用于收窄召回范围",
                             "enum": ["数码电子", "美妆护肤", "服饰运动", "食品饮料", "家居用品", "母婴用品", "运动户外", "个护清洁"]},
                "budget_max": {"type": "number", "description": "价格上限（元），用户给了预算就填"},
                "top_k": {"type": "integer", "default": 5, "description": "返回条数，默认 5"},
                "intent_hint": {"type": "string", "enum": ["recommend", "compare", "risk_check"],
                                "description": "检索意图提示，影响召回深度"},
                "min_rating": {"type": "number",
                               "description": "口碑下限(1-5)；用户要求高分/口碑好时传如 4.0"},
                "focus": {"type": "string", "enum": ["reviews", "faq"],
                          "description": "聚焦检索：reviews=只搜真实评价, faq=只搜参数问答；关心口碑/参数细节时用"},
            },
            "required": ["query"],
        },
    )

    async def run(self, ctx: ToolContext, query: str = "", category: str | None = None,
                  budget_max: float | None = None, top_k: int = 5,
                  intent_hint: str = "", min_rating: float | None = None,
                  focus: str = "") -> ToolResult:
        top_k = max(1, min(10, top_k or 5))
        # 模型工具调用不是可信的分类来源：先归一化，避免错误类别进入 DecisionAgent 的硬约束。
        category = _normalize_category(category)
        if not query:
            return await self._shallow(query, category, budget_max, top_k)
        try:
            from app.core.config import USE_V9_CHUNK_RETRIEVAL
            if USE_V9_CHUNK_RETRIEVAL:
                return await self._v9_search(ctx, query, category, budget_max, top_k, intent_hint)
        except Exception as exc:  # 新索引开关异常不阻断既有工具链
            logger.warning("v9 shopping.search degraded to legacy: %s", exc)
        try:
            # 给浅层保底预留时间，避免外层工具 8 秒熔断直接取消整个调用，
            # 导致既没有深检索结果，也来不及执行本地商品库兜底。
            products, evidence, decisions = await asyncio.wait_for(
                self._deep_search(
                    query, category, budget_max, top_k, intent_hint,
                    min_rating=min_rating, focus=focus,
                ),
                timeout=54.0,
            )
        except Exception as e:  # noqa: BLE001 — 管线异常回退浅层搜索（保底不空手）
            logger.warning(f"deep search degraded to shallow: {e}")
            shallow = await self._shallow(query, category, budget_max, top_k)
            if shallow.ok:
                shallow.message = f"深度检索降级后，{shallow.message}"
            self._write_shallow_state(ctx, shallow)
            return shallow
        # 后置口碑守卫：多通道编排的 fallback/review 源不感知 rating_min（服务端过滤
        # 仅覆盖 text 通道），按商品真实评分再拦一道——无论哪个源泄漏都不把低分货给用户
        if min_rating is not None and products:
            from app.repositories.product_repo import get_product_repo as _gpr

            _repo = _gpr()
            _kept = []
            for p in products:
                _prod = _repo.get_by_id(p.get("product_id", ""))
                _avg, _n = _avg_rating(_prod) if _prod else (0.0, 0)
                if _n and _avg >= min_rating:
                    _kept.append(p)
            products = _kept
        if not products:
            # 硬过滤（口碑下限/聚焦）零结果是有效信号：不浅层兜底（会混入不满足约束的商品），
            # 如实告知 LLM 供其引导用户放宽条件
            if min_rating is not None or focus:
                cond = f"口碑≥{min_rating}" if min_rating is not None else f"聚焦{focus}"
                return ToolResult(data={"products": []},
                                  message=f"「{query}」在条件【{cond}】下无匹配商品；"
                                          f"可建议用户放宽条件后重搜")
            # 深管线零召回（如整句口语 query）→ 浅层子串匹配再兜一道
            shallow = await self._shallow(query, category, budget_max, top_k)
            if shallow.ok and (shallow.data or {}).get("products"):
                shallow.message = f"深度检索零召回，{shallow.message}"
                self._write_shallow_state(ctx, shallow)
                return shallow

        # 写回主 state（存在时）：供最终 generate_stream 与前端商品卡消费；新结果置前去重
        st = getattr(ctx, "state", None)
        if st is not None and hasattr(st, "retrieved_products") and not getattr(st, "retrieval_groups", None):
            new_pids = {p.get("product_id") for p in products}
            st.retrieved_products = products + [
                p for p in (st.retrieved_products or []) if p.get("product_id") not in new_pids]
            st.evidence_list = (evidence or []) + [
                e for e in (st.evidence_list or []) if e.get("product_id") not in new_pids]
            st.decision_results = (decisions or []) + [
                d for d in (st.decision_results or []) if d.get("product_id") not in new_pids]

        score_by_pid = {d.get("product_id"): d.get("final_score") for d in (decisions or [])}
        items, lines = [], []
        for i, p in enumerate(products[:top_k], 1):
            pid = p.get("product_id", "")
            item = {"product_id": pid, "title": p.get("title", ""), "brand": p.get("brand", ""),
                    "price": p.get("price", 0), "category": p.get("category", "")}
            if score_by_pid.get(pid) is not None:
                item["decision_score"] = score_by_pid[pid]
            items.append(item)
            score_txt = (f" 决策分{item['decision_score']:.2f}"
                         if item.get("decision_score") is not None else "")
            # product_id 必须进**文本**通道：res.data 会被 summarize_result 的
            # json.dumps(...)[:300] 随机腰斩，LLM 拿不到完整 id 就无法调
            # shopping.display 选品，卡片也就无从与它的分析对齐。
            lines.append(f"{i}. [{pid}] {item['brand']} {item['title'][:26]} "
                         f"¥{item['price']}{score_txt}")
        if not items:
            return ToolResult(data={"products": []}, message=f"「{query}」库内未检索到商品")
        return ToolResult(data={"products": items},
                          message=f"「{query}」深度检索到 {len(items)} 件：\n" + "\n".join(lines))

    @staticmethod
    async def _v9_search(ctx: ToolContext, query: str, category: str | None,
                         budget_max: float | None, top_k: int, intent_hint: str) -> ToolResult:
        """V9 工具调用快照。每个 ReAct 调用只追加一个 group，绝不覆盖旧组。"""
        from app.retrieval.tool_chunk_retriever_v9 import ToolChunkRetrieverV9
        from app.schemas.workflow import Constraints, RetrievalGroup, RetrievalPlan

        state = getattr(ctx, "state", None)
        plan = (getattr(state, "retrieval_plan", None) or RetrievalPlan(category=category, top_k=max(5, top_k))).model_copy(deep=True)
        constraints = (getattr(state, "constraints", None) or Constraints(category=category, budget_max=budget_max)).model_copy(deep=True)
        # 多目标请求中一次工具调用只服务自己的 Router 子目标。此前把完整
        # sub_queries 一起带进每次 search，会让“上衣”检索同时继承“鞋”的条件，
        # 既污染签名也会稀释 LLM Filter 的判断范围。
        norm_query = "".join(str(query or "").lower().split())
        matched_sub = next((sq for sq in (plan.sub_queries or [])
                            if "".join(str(sq.query or "").lower().split()) == norm_query), None)
        if matched_sub is not None:
            plan.entity_terms = list(matched_sub.entity_terms or [])
            plan.must_constraints = list(matched_sub.must_constraints or [])
            plan.soft_preferences = list(matched_sub.soft_preferences or [])
            plan.avoid_constraints = list(matched_sub.avoid_constraints or [])
            plan.evidence_focus = list(matched_sub.evidence_focus or [])
            plan.answer_goal = matched_sub.answer_goal or plan.answer_goal
            plan.ambiguity = matched_sub.ambiguity or plan.ambiguity
            plan.category = matched_sub.category or plan.category
            plan.sub_queries = []
            if matched_sub.category:
                constraints.category = matched_sub.category
            if matched_sub.budget_hint:
                constraints.budget_max = matched_sub.budget_hint
        if category:
            plan.category = constraints.category = category
        if budget_max is not None:
            constraints.budget_max = budget_max
        intent = intent_hint or getattr(state, "intent", "recommend") or "recommend"
        result = await ToolChunkRetrieverV9().search(query=query, plan=plan, constraints=constraints,
                                                     intent=intent, top_k=max(9, top_k))
        products = list(result.get("products") or [])
        if matched_sub is not None:
            # 分组归属是受控交付字段：用于首选卡覆盖、最终回答与缺组说明，
            # 不由模型自由填写，避免“零食结果被说成饮品”。
            for product in products:
                product["group_role"] = matched_sub.role or matched_sub.query
        if state is not None:
            # 分组键由受控运行时写入隔离 state；它不来自模型上下文，也不会
            # 暴露给客户端。多目标的一次 search 批次据此保留独立结果，不能互相覆盖。
            group_id = (getattr(state, "tool_runtime_group_id", "")
                        or f"tool:v9:{len(getattr(state, 'candidate_groups', []) or []) + 1}")
            ids = [p.get("product_id", "") for p in products if p.get("product_id")]
            pack = result.get("evidence_pack") or {}
            missing_reason = str((result.get("filter") or {}).get("missing_group") or "")
            state.retrieval_groups.append(RetrievalGroup(
                group_id=group_id, role=(matched_sub.role if matched_sub else "工具检索"), query=query,
                hard_constraints={"must": list(plan.must_constraints or constraints.must_tags or []),
                                  "avoid": list(plan.avoid_constraints or constraints.exclude_tags or [])},
                product_ids=ids, evidence_product_ids=list(pack), status="matched" if ids else "missing",
                missing_reason=missing_reason,
            ))
            state.candidate_groups.append({"group_id": group_id, **result})
            state.candidate_trace.append({"group_id": group_id, "signature": result.get("signature", ""),
                                          "query": query, "chunk_hits": result.get("chunk_hits", 0),
                                          "latency_ms": result.get("latency_ms", 0)})
            state.llm_filter_result[group_id] = result.get("filter") or {}
            state.evidence_packs.update(pack)
            prior = list(state.retrieved_products or [])
            state.retrieved_products = products + [p for p in prior if p.get("product_id") not in set(ids)]
            state.evidence_list = [e for rows in pack.values() for e in rows] + list(state.evidence_list or [])
        items = [{key: p.get(key) for key in ("product_id", "title", "brand", "price", "category")}
                 for p in products[:top_k]]
        lines = [f"{i}. [{item['product_id']}] {item.get('brand', '')} {item.get('title', '')[:32]} ¥{item.get('price', 0)}"
                 for i, item in enumerate(items, 1)]
        return ToolResult(data={"products": items, "filter": result.get("filter", {}), "retrieval_scope": "v9_chunk"},
                          message=(f"「{query}」已完成商品筛选：\n" + "\n".join(lines)) if items
                          else f"「{query}」未找到满足条件的商品")

    @staticmethod
    async def _deep_search(query: str, category: str | None, budget_max: float | None,
                           top_k: int, intent_hint: str,
                           min_rating: float | None = None, focus: str = ""):
        """子管线：retrieval -> reranker -> evidence_check -> decision。

        通过 framework 能力注册表按名消费（P0-1：不反向 import workflow.graph）。
        能力由 graph 模块 import 时注册：生产链路 main/run_workflow 必然已加载；
        若未注册，pipeline 抛 KeyError 由 run() 降级浅层搜索（fail-open）。

        min_rating/focus：原子检索参数（spec omni-harness D3）——口碑下限服务端过滤 +
        聚焦块类型（reviews→rev / faq→faq），供 LLM 按需精细化。"""
        from app.framework.orchestration import run_capability_pipeline
        from app.schemas.workflow import Constraints, RetrievalPlan, WorkflowState

        intent = intent_hint if intent_hint in ("recommend", "compare", "risk_check") else "recommend"
        _focus_map = {"reviews": "rev", "faq": "faq"}
        sub = WorkflowState(
            user_query=query,
            intent=intent,
            constraints=Constraints(category=category or None, budget_max=budget_max),
            retrieval_plan=RetrievalPlan(
                channels=["text", "review"], category=category or None,
                top_k=max(top_k * 2, 8 if intent != "recommend" else top_k * 2),
                rating_min=min_rating,
                chunk_focus=_focus_map.get(focus),
            ),
        )
        sub = await run_capability_pipeline(
            ["retrieval", "reranker", "evidence_check", "decision"], sub)
        return (sub.retrieved_products or [])[:top_k * 2], sub.evidence_list or [], sub.decision_results or []

    @staticmethod
    async def _shallow(query: str, category: str | None, budget_max: float | None,
                       top_k: int) -> ToolResult:
        """浅层搜索兜底（原实现）。"""
        try:
            from app.repositories.product_repo import get_product_repo

            repo = get_product_repo()
            if query:
                products = repo.search_text(query, top_k=top_k)
            else:
                products = repo.filter_by(category=category, price_max=budget_max)[:top_k]
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=str(e))
        items = [
            {"product_id": p.product_id, "title": p.title, "brand": p.brand,
             "price": p.base_price, "category": p.category}
            for p in products[:top_k]
        ]
        return ToolResult(data={"products": items}, message=f"找到 {len(items)} 个相关商品")

    @staticmethod
    def _write_shallow_state(ctx: ToolContext, result: ToolResult) -> None:
        """Mirror shallow fallback products into the workflow/SSE state."""
        if not result.ok:
            return
        fallback_products = list((result.data or {}).get("products") or [])
        if not fallback_products:
            return
        st = getattr(ctx, "state", None)
        if st is not None and hasattr(st, "retrieved_products") and not getattr(st, "retrieval_groups", None):
            new_pids = {p.get("product_id") for p in fallback_products}
            st.retrieved_products = fallback_products + [
                p for p in (st.retrieved_products or [])
                if p.get("product_id") not in new_pids
            ]


class GetProductDetailTool(Tool):
    spec = ToolSpec(
        name="shopping.detail", category="shopping", permission="read",
        description="获取单个商品详情与口碑摘要",
        parameters={
            "type": "object",
            "properties": {"product_id": {"type": "string"}},
            "required": ["product_id"],
        },
    )

    async def run(self, ctx: ToolContext, product_id: str = "") -> ToolResult:
        try:
            from app.repositories.product_repo import get_product_repo

            p = get_product_repo().get_by_id(product_id)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=str(e))
        if not p:
            return ToolResult(ok=False, message="找不到这件商品～")
        avg, n = _avg_rating(p)
        return ToolResult(
            data={
                "product_id": p.product_id, "title": p.title, "brand": p.brand,
                "price": p.base_price, "category": p.category, "sub_category": p.sub_category,
                "avg_rating": avg, "review_count": n,
                "skus": [s.model_dump() for s in (p.skus or [])],
            },
            message=f"{p.brand} {p.title}｜¥{p.base_price:.0f}｜口碑 {avg}/5（{n}条）",
        )


class ProductDossierTool(Tool):
    """为一个已可信锁定的商品建立完整且可引用的档案。

    该工具与 ``shopping.search`` 并列而不是其包装：前者找候选，后者只读取
    一个主体的结构化资料，避免点选后又让泛检索混入同类或配件。
    """

    spec = ToolSpec(
        name="shopping.product_dossier", category="shopping", permission="read",
        timeout_ms=12_000,
        description=(
            "深入核对一件已锁定商品的完整档案：规格、官方说明、FAQ、真实评价、"
            "风险与信息缺口，并返回可引用证据。仅当 product_id 已由点选、实体解析或"
            "图片识别可信锁定，且用户问详细介绍、优缺点、参数、口碑、是否适合时调用。"
            "不要用它找商品或做泛推荐；未锁定商品先用 shopping.search 或向用户澄清。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "可信锁定的商品 ID；必须来自当前锁定主体或已检索候选。",
                },
                "focus": {
                    "type": "string",
                    "enum": ["overview", "specs", "reviews", "faq", "risks", "suitability"],
                    "default": "overview",
                    "description": "用户特别关心的角度；overview 为完整概览。",
                },
            },
            "required": ["product_id"],
        },
    )

    @staticmethod
    def _state_item(product) -> dict:
        return {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "sub_category": product.sub_category,
            "price": product.base_price,
            # 图片文件缺失时图片端点仍能返回统一占位响应；不要因为 image_path
            # 为空就把协议字段删掉，否则聊天卡片只会静默显示破图。
            "image_urls": [f"/api/products/{product.product_id}/image"],
            "skus": [sku.model_dump() for sku in (product.skus or [])],
            "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else {},
        }

    @staticmethod
    def _build_dossier(product, focus: str) -> tuple[dict, list[dict]]:
        rk = product.rag_knowledge
        description = (rk.marketing_description or "").strip() if rk else ""
        faqs = list(rk.official_faq or []) if rk else []
        reviews = list(rk.user_reviews or []) if rk else []
        ratings = [int(r.rating) for r in reviews if isinstance(r.rating, int)]
        rating_counts = Counter(ratings)
        review_count = len(ratings)
        avg_rating = round(sum(ratings) / review_count, 1) if review_count else None
        positive_count = sum(1 for r in ratings if r >= 4)
        risk_count = sum(1 for r in ratings if r <= 2)

        evidence: list[dict] = []
        if description:
            evidence.append({
                "evidence_id": f"E-MKT-{product.product_id}-0",
                "source_type": "marketing", "source_id": product.product_id,
                "product_id": product.product_id, "confidence": 0.72,
                "content": f"[商品说明] {description[:500]}",
            })
        for idx, faq in enumerate(faqs[:6]):
            evidence.append({
                "evidence_id": f"POL-{product.product_id}-{idx}",
                "source_type": "official_faq", "source_id": f"{product.product_id}:faq:{idx}",
                "product_id": product.product_id, "confidence": 0.90,
                "content": f"[官方问答] {faq.question[:100]}：{faq.answer[:260]}",
            })

        # 保留低分与高分评价，避免档案只挑正面证据；同一评价只出现一次。
        picked: list[tuple[int, object]] = []
        for idx, review in enumerate(reviews):
            if review.rating <= 2:
                picked.append((idx, review))
                if len([r for _, r in picked if r.rating <= 2]) >= 2:
                    break
        for idx, review in enumerate(reviews):
            if review.rating >= 4 and all(idx != old_idx for old_idx, _ in picked):
                picked.append((idx, review))
                if len(picked) >= 5:
                    break
        for idx, review in picked[:5]:
            evidence.append({
                "evidence_id": f"R-{product.product_id}-{idx}",
                "source_type": "user_review_risk" if review.rating <= 2 else "user_review_positive",
                "source_id": f"{product.product_id}:review:{idx}",
                "product_id": product.product_id, "confidence": 0.68,
                "content": f"[用户评价] {review.nickname[:30]}（{review.rating}星）：{review.content[:260]}",
            })

        sku_rows = [
            {"sku_id": sku.sku_id, "properties": sku.properties, "price": sku.price}
            for sku in (product.skus or [])[:8]
        ]
        sku_prices = [float(s.price) for s in (product.skus or [])]
        gaps: list[str] = []
        if not description:
            gaps.append("缺少商品说明")
        if not faqs:
            gaps.append("暂无官方问答")
        if not reviews:
            gaps.append("暂无用户评价")
        if not sku_rows:
            gaps.append("暂无可用规格信息")
        safe_focus = focus if focus in {"overview", "specs", "reviews", "faq", "risks", "suitability"} else "overview"
        dossier = {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "sub_category": product.sub_category,
            "price": product.base_price,
            "focus": safe_focus,
            "marketing_description": description[:900],
            "skus": sku_rows,
            "price_range": {
                "min": min(sku_prices) if sku_prices else product.base_price,
                "max": max(sku_prices) if sku_prices else product.base_price,
            },
            "official_faq": [{"question": f.question[:120], "answer": f.answer[:320]} for f in faqs[:6]],
            "review_summary": {
                "count": review_count,
                "avg_rating": avg_rating,
                "positive_count": positive_count,
                "risk_count": risk_count,
                "rating_distribution": {str(k): rating_counts[k] for k in sorted(rating_counts)},
            } if review_count else None,
            "information_gaps": gaps,
            "evidence_ids": [item["evidence_id"] for item in evidence],
            "evidence_status": "信息有限" if gaps else "证据充分",
        }
        return dossier, evidence

    async def run(self, ctx: ToolContext, product_id: str = "", focus: str = "overview") -> ToolResult:
        product_id = (product_id or "").strip()
        state = getattr(ctx, "state", None)
        if not product_id:
            return ToolResult(ok=False, message="请先锁定要分析的商品。")

        # 点选/精确实体命中时，工具只能读取该可信主体；防模型借参数越界。
        locked = (getattr(state, "focus_product_id", "") or "").strip() if state is not None else ""
        if locked and product_id != locked:
            return ToolResult(ok=False, message="该商品不在当前已锁定范围内，请围绕已锁定商品继续分析。")
        if not locked and state is not None:
            # A dossier is a single-subject analysis tool, not a way for ReAct
            # to promote one item from a multi-product recommendation.  Such a
            # promotion used to overwrite all group candidates.
            groups = getattr(state, "retrieval_groups", []) or []
            scope = getattr(state, "retrieval_scope", "broad") or "broad"
            resolved_list = list(getattr(state, "resolved_product_ids", []) or [])
            if groups and not (scope == "exact_product" and len(resolved_list) == 1):
                return ToolResult(ok=False, message="当前是多商品推荐，未锁定单一主体；如需单品档案，请先点选一件商品再问欧米。")
            resolved = set(getattr(state, "resolved_product_ids", []) or [])
            retrieved = {p.get("product_id") for p in (getattr(state, "retrieved_products", []) or [])}
            if resolved and product_id not in resolved:
                return ToolResult(ok=False, message="该商品不在当前可信解析范围内，请先检索或澄清。")
            if not resolved and retrieved and product_id not in retrieved:
                return ToolResult(ok=False, message="该商品尚未检索到，请先使用 shopping.search。")
        # 档案一次构建即覆盖概览、规格、FAQ、评价与风险；focus 只是回答角度，
        # 不能成为重复读取同一商品、重复跑 DecisionAgent 的理由。
        cached = (getattr(state, "product_dossiers", {}) or {}).get(product_id) if state is not None else None
        if cached:
            return ToolResult(
                data={
                    "product_id": product_id,
                    "title": cached.get("title", ""),
                    "evidence_status": cached.get("evidence_status", "信息有限"),
                    "evidence_ids": cached.get("evidence_ids", []),
                    "information_gaps": cached.get("information_gaps", []),
                },
                message=f"「{cached.get('brand', '')} {cached.get('title', '')}」的完整档案已在本轮建立，可直接据此回答。",
            )
        try:
            from app.repositories.product_repo import get_product_repo

            product = get_product_repo().get_by_id(product_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("product dossier lookup failed: %s", exc)
            return ToolResult(ok=False, error=str(exc))
        if not product:
            return ToolResult(ok=False, message="没有找到这件商品，无法建立档案。")

        dossier, evidence = self._build_dossier(product, focus)
        if state is not None:
            item = self._state_item(product)
            # dossier 负责补全商品事实，不能把调用前已经得出的“本轮筛选结论”
            # 清掉。否则深度模式在建立档案后会丢失 specific scenario 的
            # conditional 标记，出现普通模式 65、深度模式却 92 的评分漂移。
            previous = next(
                (candidate for candidate in (state.retrieved_products or [])
                 if candidate.get("product_id") == product.product_id),
                {},
            )
            for key in ("filter_bucket", "card_reason", "group_role"):
                if previous.get(key):
                    item[key] = previous[key]
            state.focus_product_id = product.product_id
            state.retrieval_scope = "exact_product"
            state.resolved_product_ids = [product.product_id]
            # 单品档案默认只交付主体，不让旧候选或同类商品出现在卡片中。
            state.retrieved_products = [item]
            state.evidence_list = evidence
            state.product_dossiers[product.product_id] = dossier
            if not state.product_resolution:
                state.product_resolution = {
                    "match_type": "exact_product", "retrieval_scope": "exact_product",
                    "product_id": product.product_id, "resolved_product_ids": [product.product_id],
                    "confidence": 1.0, "label": f"已锁定：{product.brand} {product.title}",
                }
            state.selected_products = [item]
            state.selected_reason = "已锁定商品的深度档案"
            # 完整档案只保存在请求状态；ConversationContextAssembler 会按预算抽取
            # 需要的结构化事实，最终回答绝不读取工具转录或 context_prompt。
            try:
                from app.agents.decision_agent import DecisionAgent

                await DecisionAgent().execute(state)
            except Exception as exc:  # noqa: BLE001
                logger.warning("product dossier decision degraded: %s", exc)

        reviews = dossier.get("review_summary") or {}
        review_txt = (
            f"口碑 {reviews.get('avg_rating')}/5（{reviews.get('count')} 条）"
            if reviews else "暂无用户评价"
        )
        return ToolResult(
            data={
                "product_id": product.product_id,
                "title": product.title,
                "evidence_status": dossier["evidence_status"],
                "evidence_ids": dossier["evidence_ids"],
                "information_gaps": dossier["information_gaps"],
            },
            message=(f"已建立「{product.brand} {product.title}」深度档案："
                     f"{len(dossier['skus'])} 个规格、{len(dossier['official_faq'])} 条官方问答、{review_txt}。"
                     f"回答只能围绕该商品，并说明 {dossier['evidence_status']}。"),
        )


def build_product_dossier(product, focus: str = "overview") -> dict:
    """无工具上下文的可复用档案构建，供问欧米/对比轻量链直接调用。"""
    dossier, _ = ProductDossierTool._build_dossier(product, focus)
    return dossier


class CompareProductsTool(Tool):
    spec = ToolSpec(
        name="shopping.compare", category="shopping", permission="read",
        description="对比多个商品的价格与口碑",
        parameters={
            "type": "object",
            "properties": {"product_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["product_ids"],
        },
    )

    async def run(self, ctx: ToolContext, product_ids: list | None = None) -> ToolResult:
        product_ids = product_ids or []
        if len(product_ids) < 2:
            return ToolResult(ok=False, message="请至少提供两个商品来对比～")
        try:
            from app.repositories.product_repo import get_product_repo

            repo = get_product_repo()
            rows = []
            for pid in product_ids[:5]:
                p = repo.get_by_id(pid)
                if not p:
                    continue
                avg, n = _avg_rating(p)
                rows.append({"product_id": p.product_id, "title": p.title, "brand": p.brand,
                             "price": p.base_price, "avg_rating": avg, "review_count": n})
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=str(e))
        if len(rows) < 2:
            return ToolResult(ok=False, message="有效商品不足两个，无法对比～")
        return ToolResult(data={"comparison": rows}, message=f"已对比 {len(rows)} 款商品")


class CheckInventoryTool(Tool):
    """查询商品库存（经 InventoryProvider）。"""

    spec = ToolSpec(
        name="shopping.check_inventory", category="shopping", permission="read",
        description="查询商品库存",
        parameters={
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "sku_id": {"type": "string"},
            },
            "required": ["product_id"],
        },
    )

    async def run(self, ctx: ToolContext, product_id: str = "", sku_id: str | None = None) -> ToolResult:
        if not product_id:
            return ToolResult(ok=False, message="请先看看商品哦～")
        try:
            from app.providers.tools.mocks import get_inventory_provider
            from app.repositories.product_repo import get_product_repo

            p = get_product_repo().get_by_id(product_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"check_inventory failed: {e}")
            return ToolResult(ok=False, message="暂时无法查询库存～")
        if not p:
            return ToolResult(ok=False, message="找不到这件商品～")
        info = await get_inventory_provider().check(product_id, sku_id)
        name = f"{p.brand} {p.title}"
        level = info.get("level", "")
        qty = info.get("quantity", 0)
        eta = info.get("eta", "")
        if level == "out":
            msg = f"「{name}」暂时缺货～"
        elif level == "low":
            msg = f"「{name}」低库存（仅剩 {qty} 件），要下单赶紧哦～"
        else:
            eta_s = f" · 预计 {eta} 送达" if eta else ""
            msg = f"「{name}」有货 · 库存 {qty}{eta_s}"
        return ToolResult(message=msg, data={"inventory": info, "product_id": product_id})


class DisplayProductsTool(Tool):
    """LLM 显式声明"要给用户展示哪几件商品"。

    这是卡片与答文的**唯一真源**：调用后 ``state.selected_products`` 被写入，
    SSE 层的商品卡与 ``ResponseAgent._context_products`` 的候选集都只认它。

    为什么做成工具而不是图节点：ReAct 循环里 LLM 推理完就知道要推哪几款，此刻声明
    最准；做成节点要多一次 LLM 调用，且节点选完后 LLM 写回答时仍可能改主意，
    等于又回到两套口径。

    代价是依赖 LLM 主动调用。SSE 层保留了"从终稿反推引用集"的兜底，未调时不至于
    退化成随机原序。
    """

    spec = ToolSpec(
        name="shopping.display", category="shopping", permission="read",
        timeout_ms=2000,
        description=(
            "确认要展示给用户的商品卡片。检索完、想清楚推荐哪几款之后调用，"
            "只传你在回答里真正会讲到的商品；不调用则前端卡片只能靠文本猜测，可能和你讲的对不上"
        ),
        parameters={
            "type": "object",
            "properties": {
                "product_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "要展示的 product_id 列表，按推荐优先级排序，"
                                   "取自 shopping.search 返回行首的 [id]",
                },
                "reason": {"type": "string",
                           "description": "一句话说明为什么选这几款（会作为答文依据）"},
            },
            "required": ["product_ids"],
        },
    )

    async def run(self, ctx, product_ids: list | None = None, reason: str = "",
                  **kw) -> ToolResult:
        state = getattr(ctx, "state", None)
        if state is None or not hasattr(state, "retrieved_products"):
            return ToolResult(ok=False, error="no_state")
        ids = [str(i) for i in (product_ids or []) if i]
        if not ids:
            return ToolResult(ok=False, message="未提供 product_ids，请先检索再选品")

        # 只认已召回集合里的 id —— 防 LLM 编造，也防它引用上一轮已失效的商品
        pool = {p.get("product_id"): p for p in (state.retrieved_products or [])
                if p.get("product_id")}
        chosen = [pool[i] for i in ids if i in pool]
        unknown = [i for i in ids if i not in pool]
        if not chosen:
            return ToolResult(
                ok=False,
                message=f"这些 id 不在已检索结果里：{unknown[:5]}；请先 shopping.search 再选品")

        state.selected_products = chosen
        state.selected_reason = reason or ""
        msg = f"已确认展示 {len(chosen)} 件：" + "、".join(
            f"{p.get('brand', '')}{p.get('title', '')[:14]}" for p in chosen)
        if unknown:
            msg += f"（忽略了不在检索结果里的 {len(unknown)} 个 id）"
        return ToolResult(message=msg,
                          data={"selected": [p.get("product_id") for p in chosen]})
