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

        # V9 把普通推荐和 shopping.search 收敛到同一“工具调用级”检索服务。
        # 旧编排保留为开关关闭时的完整回退，不混合两套候选以免旧评论块重新串入。
        try:
            from app.core.config import USE_V9_CHUNK_RETRIEVAL
            if USE_V9_CHUNK_RETRIEVAL:
                from app.retrieval.tool_chunk_retriever_v9 import ToolChunkRetrieverV9
                from app.schemas.workflow import RetrievalGroup

                result = await ToolChunkRetrieverV9(self._repo).search(
                    query=state.user_query, plan=plan, constraints=c, intent=state.intent,
                    top_k=9,
                )
                if not result.get("chunk_hits"):
                    # 集合未构建/服务不可达与“真实无匹配”在 V9 检索器内部不可完全
                    # 区分；主链此处回退旧召回，避免错误地给用户空结果。
                    raise RuntimeError("v9 index returned no chunk hits")
                state.retrieved_products = list(result.get("products") or [])
                state.evidence_list = [e for pack in (result.get("evidence_pack") or {}).values() for e in pack]
                group_id = f"v9:{len(state.candidate_groups) + 1}"
                ids = [p.get("product_id", "") for p in state.retrieved_products if p.get("product_id")]
                status = "matched" if ids else "missing"
                missing = str((result.get("filter") or {}).get("missing_group") or "")
                state.retrieval_groups = [RetrievalGroup(
                    group_id=group_id, role="主需求", query=state.user_query,
                    hard_constraints={"must": list(plan.must_constraints or c.must_tags or []),
                                      "avoid": list(plan.avoid_constraints or c.exclude_tags or [])},
                    product_ids=ids, evidence_product_ids=list((result.get("evidence_pack") or {}).keys()),
                    status=status, missing_reason=missing,
                )]
                state.candidate_groups.append({"group_id": group_id, **result})
                state.candidate_trace.append({"group_id": group_id, "signature": result.get("signature", ""),
                                              "query": state.user_query, "chunk_hits": result.get("chunk_hits", 0),
                                              "latency_ms": result.get("latency_ms", 0), "source": "v9"})
                state.llm_filter_result[group_id] = result.get("filter") or {}
                state.evidence_packs.update(result.get("evidence_pack") or {})
                state.structured_retrieval_report = {"version": "v9", "group_id": group_id,
                                                     "filter_status": (result.get("filter") or {}).get("status", ""),
                                                     "missing_reason": missing}
                return self._finish_trace(state, f"v9 products={len(ids)}, chunks={result.get('chunk_hits', 0)}, filter={(result.get('filter') or {}).get('status', '')}")
        except Exception as exc:  # V9 影子/开关问题绝不能让推荐变空
            logger.warning("v9 retrieval degraded to legacy: %s", exc)

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
            products = list(bundle.products or [])
            # V8: facts decide eligibility for explicit food constraints.  The
            # discovery index is a candidate source, never an opaque replacement
            # for the existing multi-source retrieval pipeline.
            try:
                from app.core.config import USE_DISCOVERY_V8
                from app.retrieval.discovery_retriever import DiscoveryRetriever
                from app.services.product_facts import food_constraint_groups

                food_query = (
                    (c.category or plan.category) == "食品饮料"
                    or bool(food_constraint_groups(state.user_query, list(c.must_tags or [])))
                    or any(term in state.user_query for term in ("不想长胖", "控卡", "轻负担", "减脂"))
                )
                # Once v8 is enabled it becomes the candidate-discovery source
                # for every category, not only food.  Before that rollout, food
                # facts remain the narrow, safe enhancement to legacy recall.
                if food_query or USE_DISCOVERY_V8:
                    discovery, fact_report = await DiscoveryRetriever(self._repo).search(
                        state.user_query, category=c.category or plan.category,
                        budget_max=c.budget_max, top_k=max(plan.top_k, 8),
                        must_tags=list(c.must_tags or []),
                    )
                    state.structured_retrieval_report = fact_report
                else:
                    discovery, fact_report = [], {"applied": False, "reason": "not_food_fact_query"}
                v8_discovery = bool(discovery) and discovery[0].get("discovery_source") == "v8_dense"
                if fact_report.get("applied"):
                    allowed = {p.get("product_id") for p in discovery}
                    # When a user explicitly asks for low/zero sugar/fat etc., a
                    # legacy semantic hit without the fact is not eligible.
                    legacy = [p for p in products if p.get("product_id") in allowed]
                    merged, seen = [], set()
                    for item in discovery + legacy:
                        pid = item.get("product_id")
                        if pid and pid not in seen:
                            seen.add(pid)
                            merged.append(item)
                    products = merged
                    state.trace_steps.append({
                        "step_id": f"T{len(state.trace_steps) + 1:03d}",
                        "agent_name": "Structured Discovery",
                        "action": "source_backed_fact_filter",
                        "input_summary": str(fact_report.get("required", []))[:120],
                        "output_summary": f"eligible={len(products)} source={discovery[0].get('discovery_source') if discovery else 'none'}",
                        "latency_ms": 0, "status": "success" if products else "fallback",
                    })
                elif v8_discovery:
                    # v8 has one review-free document per product. It should be
                    # the primary discovery order after shadow validation. Keep
                    # legacy only as a shortfall safety net, not a co-equal pool
                    # that lets arbitrary review chunks dominate again.
                    merged, seen = [], set()
                    for item in discovery + (products if len(discovery) < _MIN_RESULTS else []):
                        pid = item.get("product_id")
                        if pid and pid not in seen:
                            seen.add(pid)
                            merged.append(item)
                    products = merged
                    state.structured_retrieval_report = dict(fact_report, discovery_source="v8")

                # Facts that admit a product to a nutrition-constrained result
                # are themselves evidence. Keep them alongside RAG evidence so
                # answer, cards and Guard share the same traceability.
                fact_evidence: list[dict] = []
                if fact_report.get("applied"):
                    for item in discovery:
                        for fact in item.get("product_facts", []) or []:
                            if not str(fact.get("fact_key", "")).startswith("nutrition."):
                                continue
                            fact_evidence.append({
                                "evidence_id": f"fact:{item.get('product_id')}:{fact.get('fact_key')}:{fact.get('value_text')}",
                                "product_id": item.get("product_id"),
                                "source_type": "catalog_fact", "modality": "text",
                                "content": fact.get("source_text", ""),
                                "fact_key": fact.get("fact_key", ""),
                                "verified": bool(fact.get("verified", False)), "confidence": 1.0,
                            })
                v8_evidence: list[dict] = []
                if v8_discovery and products:
                    from app.retrieval.evidence_retriever import EvidenceRetriever

                    v8_evidence = await EvidenceRetriever().search(
                        state.user_query, [p.get("product_id") for p in products], max_per_product=2
                    )
                existing_evidence = list(bundle.evidence or [])
                # v8 evidence is candidate-scoped; legacy evidence is retained
                # only for those same products as a resilient transition path.
                candidate_ids = {p.get("product_id") for p in products if p.get("product_id")}
                if v8_evidence:
                    existing_evidence = [e for e in existing_evidence if e.get("product_id") in candidate_ids]
                seen_evidence = {e.get("evidence_id") for e in existing_evidence if isinstance(e, dict)}
                bundle.evidence = existing_evidence + [
                    e for e in fact_evidence + v8_evidence if e.get("evidence_id") not in seen_evidence
                ]
            except Exception as exc:  # structured layer cannot take down legacy retrieval
                logger.warning("structured discovery degraded: %s", exc)
            # 同款变体去重兑底（spec §2）：多通道融合/精排会把检索层已折叠的
            # 同款条目重新带回（实拍：森田面膜 25片装/25ml*10片 两条同时上卡），
            # 故在最终装配点再折一次 —— 统一用检索层的同款判定键。
            # 网格修整：前端每行 3 卡，末行落单 1 个最丑（4→3/7→6）。在装配终点修整
            # 而非 SSE 出口，保证候选/决策/下发/展示四层同一口径（否则会出现
            # 回答讲了 4 款、卡片只列 3 款的错位，实拍坐实）。
            from app.core.display import trim_for_grid

            state.retrieved_products = trim_for_grid(self._dedupe_variants(products))
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
