"""语义召回源（stage=recall）—— 平移自 ``retrieval_agent._text_channel`` 的检索部分。

包裹现有 ``TextRetriever``（Embedding + Qdrant ANN + 本地余弦降级 + chunk 检索），
保留子品类无结果自动放宽、品类无结果回退全库的多级放宽逻辑，并产出 text_retrieval
证据。

设计取舍：``is_required=False``。现实现中语义检索失败会内部降级到关键词/空结果，
再由 Response 走「未找到匹配」模板兜底，**从不因检索失败中断请求**。因此把它建模为
「非必需、可降级」最忠实于现有主链路（避免误用 required 在超时时上抛而破坏 SSE）。
"""

from __future__ import annotations

import logging

from app.framework.registry import component
from app.framework.retrieval.source import STAGE_RECALL, RecallSource
from app.framework.retrieval.types import RetrievalQuery, RetrievalResult
from app.providers.recall.evidence import evidence_content_for_id, text_confidence

logger = logging.getLogger(__name__)


@component(kind="recall_source", name="semantic", priority=10)
class SemanticRecallSource(RecallSource):
    """商品语义检索召回源。"""

    name = "semantic"
    priority = 10
    latency_budget_ms = 6000
    is_required = False
    stage = STAGE_RECALL

    def __init__(self, repo=None) -> None:
        from app.repositories.product_repo import ProductRepository
        from app.retrieval.text_retriever import TextRetriever

        self._repo = repo or ProductRepository()
        self._tr = TextRetriever(self._repo)

    def should_activate(self, query: RetrievalQuery) -> bool:
        channels = query.metadata.get("channels")
        if channels is None:
            return True
        return "text" in channels

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        search_query = query.effective_query

        async def _do_search(sub_cat: str | None) -> list[dict]:
            try:
                return await self._tr.search_chunked(
                    query=search_query,
                    top_k=query.top_k,
                    category=query.category,
                    sub_category=sub_cat,
                    price_max=query.budget_max,
                    price_min=query.budget_min,
                    rating_min=query.rating_min,
                    chunk_focus=query.chunk_focus,
                )
            except Exception:  # noqa: BLE001
                return await self._tr.search(
                    query=search_query,
                    top_k=query.top_k,
                    category=query.category,
                    sub_category=sub_cat,
                    price_max=query.budget_max,
                    price_min=query.budget_min,
                )

        sub_cat = query.sub_category
        results = await _do_search(sub_cat)

        # 子品类无结果 → 放宽 sub_category
        if not results and sub_cat:
            results = await _do_search(None)

        # 品类也无结果 → 回退全品类
        if not results and query.category:
            try:
                results = await self._tr.search_chunked(
                    query=search_query,
                    top_k=query.top_k,
                    category=None,
                    sub_category=None,
                    price_max=query.budget_max,
                    price_min=query.budget_min,
                    rating_min=query.rating_min,
                    chunk_focus=query.chunk_focus,
                )
            except Exception:  # noqa: BLE001
                results = await self._tr.search(
                    query=search_query,
                    top_k=query.top_k,
                    category=None,
                    sub_category=None,
                    price_max=query.budget_max,
                    price_min=query.budget_min,
                )

        evidence = self._build_text_evidence(results)
        return RetrievalResult(source_name=self.name, products=results, evidence=evidence)

    @staticmethod
    def _build_text_evidence(results: list[dict]) -> list[dict]:
        """从检索结果构建 text_retrieval 证据（R-* 评论证据由 enrich 阶段负责）。"""
        evidence: list[dict] = []
        for item in results:
            raw_score = item.get("score", 0)
            confidence = text_confidence(raw_score)
            rk = item.get("rag_knowledge")
            for eid in item.get("evidence_ids", []):
                if eid.startswith("R-"):
                    continue
                content = evidence_content_for_id(eid, rk, raw_score)
                evidence.append(
                    {
                        "evidence_id": eid,
                        "source_type": "text_retrieval",
                        "source_id": item["product_id"],
                        "product_id": item["product_id"],
                        "content": content[:200],
                        "modality": "text",
                        "confidence": confidence,
                    }
                )
        return evidence
