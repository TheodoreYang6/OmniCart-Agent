"""购物核心工具族 —— 只读检索 / 详情 / 对比。

Phase 1 仅注册 + 单测，暂不接入实时 SSE 路径（供后续 Planner 动态调用）。
包装现有 ``product_repo`` 能力，不引入新依赖。
"""

from __future__ import annotations

import asyncio
import logging

from app.framework.tools.protocols import Tool, ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

__all__ = ["SearchProductsTool", "GetProductDetailTool", "CompareProductsTool", "CheckInventoryTool"]


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
                "query": {"type": "string", "description": "检索词（品牌/品类/需求描述）"},
                "category": {"type": "string"},
                "budget_max": {"type": "number"},
                "top_k": {"type": "integer", "default": 5},
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
        if not query:
            return await self._shallow(query, category, budget_max, top_k)
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
        if st is not None and hasattr(st, "retrieved_products"):
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
            score_txt = (f"（决策分{item['decision_score']:.2f}）"
                         if item.get("decision_score") is not None else "")
            lines.append(f"{i}. {item['brand']} {item['title'][:30]} ¥{item['price']}{score_txt}")
        if not items:
            return ToolResult(data={"products": []}, message=f"「{query}」库内未检索到商品")
        return ToolResult(data={"products": items},
                          message=f"「{query}」深度检索到 {len(items)} 件：\n" + "\n".join(lines))

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
        if st is not None and hasattr(st, "retrieved_products"):
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
