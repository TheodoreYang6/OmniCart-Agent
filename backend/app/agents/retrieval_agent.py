"""V2 Retrieval Agent — 委托 RAG 框架编排器（framework.retrieval）执行多源检索。

重构（Phase 1，借鉴 amap ``libs/knowledge_base`` 的框架-实现分离）：
原「文本/评论/政策三通道 + 补充证据 + 去重」的内联实现，已抽取为
``app.providers.recall`` 下的独立 RecallSource。本 Agent 只负责：

1. 从 WorkflowState 构建 :class:`RetrievalQuery`；
2. 调 :class:`RetrievalOrchestrator` 的 6 阶段管线
   （改写 → 激活 → 并行+双超时 → 处理 → 融合 → 兜底/增强）；
3. 把 ``bundle.products`` / ``bundle.evidence`` 写回 state。

产出的 ``retrieved_products`` / ``evidence_list`` 结构与旧实现一致，
下游 Decision / Guard / Android 无感。旧的通道方法已迁移到 providers/recall。
"""

import logging

from app.agents.base import BaseAgent
from app.framework.retrieval import RetrievalOrchestrator, RetrievalQuery, SourceRegistry
from app.framework.retrieval.fusion import RRFFusion
from app.providers.recall import builtin, default_rewriter
from app.repositories.product_repo import ProductRepository
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState

logger = logging.getLogger(__name__)

# 检索整体时间预算（ms）。真实最坏延迟（embedding + Qdrant ANN）通常 <1s，
# 8s 预算既提供「整体超时 + per-source 熔断」双超时兜底，又不在正常场景误伤。
_RETRIEVAL_TIME_BUDGET_MS = 8000

# 主召回商品数低于该阈值触发 fallback 补充召回（对齐旧实现的 `< 3`）。
_MIN_RESULTS = 3


class RetrievalAgent(BaseAgent):

    def __init__(self, repo: ProductRepository | None = None):
        super().__init__()
        self._repo = repo or ProductRepository()
        registry = SourceRegistry.default(builtin=lambda: builtin(self._repo))
        self._orchestrator = RetrievalOrchestrator(
            registry,
            rewriter=default_rewriter(),
            fusion=RRFFusion(),  # 向量(semantic) + 词面(keyword) 两路 RRF 融合
            time_budget_ms=_RETRIEVAL_TIME_BUDGET_MS,
        )

    def _dedupe_variants(self, products: list[dict]) -> list[dict]:
        """折叠同款变体（spec §2）：同组保留首位（得分最高），余者记入 variant_count。

        判定键复用 SemanticRetriever._variant_key（品牌+子品类+归一标题），
        保证检索层与装配层判同款的口径一致。归一异常时原样返回（降级）。
        """
        if not products:
            return products
        try:
            from types import SimpleNamespace

            from app.retrieval.semantic_retriever import SemanticRetriever

            kept: list[dict] = []
            seen: dict[tuple, dict] = {}
            for p in products:
                key = SemanticRetriever._variant_key(SimpleNamespace(
                    title=p.get("title", ""), brand=p.get("brand", ""),
                    sub_category=p.get("sub_category", "")))
                first = seen.get(key)
                if first is not None:
                    first["variant_count"] = int(first.get("variant_count") or 0) + 1
                    ids = first.setdefault("variant_product_ids", [])
                    if len(ids) < 5 and p.get("product_id"):
                        ids.append(p["product_id"])
                    continue
                seen[key] = p
                kept.append(p)
            return kept
        except Exception as e:  # noqa: BLE001 — 去重失败不得丢商品
            logger.debug(f"同款去重跳过: {e}")
            return products

    def _build_card(self) -> AgentCard:
        return AgentCard(
            agent_id="retrieval",
            name="Retrieval Agent",
            description="多路证据检索：文本检索 + 评论挖掘 + 政策查询",
            capabilities=["text_retrieval", "review_mining", "policy_search", "evidence_collection"],
            input_schema={"retrieval_plan": "RetrievalPlan", "constraints": "Constraints"},
            output_schema={"retrieved_products": "list[dict]", "evidence_list": "list[dict]"},
        )

    async def execute(self, state: WorkflowState) -> WorkflowState:
        plan = state.retrieval_plan
        c = state.constraints
        self._start_trace(
            state,
            "multi_channel_retrieval",
            f"channels={plan.channels}, cat={c.category}, top_k={plan.top_k}",
        )

        try:
            query = RetrievalQuery(
                query=state.user_query,
                category=c.category or plan.category,
                sub_category=c.sub_category or plan.sub_category,
                budget_max=c.budget_max,
                budget_min=c.budget_min,
                scenario=c.scenario,
                must_tags=list(c.must_tags or []),
                spec_keywords=list(getattr(c, "spec_keywords", []) or []),
                exclude_tags=list(c.exclude_tags or []),
                top_k=plan.top_k,
                min_results=_MIN_RESULTS,
                rating_min=plan.rating_min,
                chunk_focus=plan.chunk_focus,
                context=state.context_prompt or "",
                metadata={"channels": list(plan.channels or [])},
            )

            bundle = await self._orchestrator.retrieve(query)
            # 同款变体去重兑底（spec §2）：多通道融合/精排会把检索层已折叠的
            # 同款条目重新带回（实拍：森田面膜 25片装/25ml*10片 两条同时上卡），
            # 故在最终装配点再折一次 —— 统一用检索层的同款判定键。
            # 网格修整：前端每行 3 卡，末行落单 1 个最丑（4→3/7→6）。在装配终点修整
            # 而非 SSE 出口，保证候选/决策/下发/展示四层同一口径（否则会出现
            # 回答讲了 4 款、卡片只列 3 款的错位，实拍坐实）。
            from app.core.display import trim_for_grid

            state.retrieved_products = trim_for_grid(self._dedupe_variants(bundle.products))
            state.evidence_list = bundle.evidence

            # 记录 query 改写 trace（发生改写时，供 AgentTracePanel 展示）
            if query.rewritten_query and query.rewritten_query != state.user_query:
                state.trace_steps.append(
                    {
                        "step_id": f"T{len(state.trace_steps) + 1:03d}",
                        "agent_name": "Retrieval Agent (Query Rewrite)",
                        "action": "query_rewrite",
                        "input_summary": state.user_query[:60],
                        "output_summary": query.rewritten_query[:80],
                        "latency_ms": 0,
                        "status": "success",
                    }
                )

            dropped = f", dropped={bundle.dropped_sources}" if bundle.dropped_sources else ""
            summary = (
                f"products={len(state.retrieved_products)}, "
                f"evidence={len(bundle.evidence)}, "
                f"channels={len(plan.channels)}(orchestrated){dropped}"
            )
            return self._finish_trace(state, summary)

        except Exception as e:
            return self._error_trace(state, str(e))
