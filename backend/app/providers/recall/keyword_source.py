"""关键词召回源 (V5, stage=recall) — PG pg_trgm 词相似度检索。

与语义召回 (SemanticRecallSource, 向量 ANN) 并列作为混合检索的**词面**通道：
对精确词/型号/品牌等语义向量易漏召的 query 提供互补召回。两路结果由编排器的
RRFFusion 融合，再由 Reranker (gte-rerank-v2) 精排。

依赖 PgProductRepository._akeyword_search（基于 products.search_text + word_similarity）。
JSON 降级模式下该源自动空返回（语义源仍可用本地缓存兜底）。
"""

from __future__ import annotations

import logging

from app.framework.registry import component
from app.framework.retrieval.source import STAGE_RECALL, RecallSource
from app.framework.retrieval.types import RetrievalQuery, RetrievalResult

logger = logging.getLogger(__name__)


@component(kind="recall_source", name="keyword", priority=20)
class KeywordRecallSource(RecallSource):
    """PG 关键词（trigram）召回源。"""

    name = "keyword"
    priority = 20
    latency_budget_ms = 3000
    is_required = False
    stage = STAGE_RECALL

    def __init__(self, repo=None) -> None:
        from app.repositories.product_repo import ProductRepository
        from app.retrieval.text_retriever import TextRetriever

        self._repo = repo or ProductRepository()
        self._tr = TextRetriever(self._repo)  # 复用 _product_to_result 构造统一契约

    def should_activate(self, query: RetrievalQuery) -> bool:
        channels = query.metadata.get("channels")
        if channels is None:
            return True
        return "text" in channels

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        akw = getattr(self._repo, "_akeyword_search", None)
        if akw is None:
            # JSON 降级模式无 PG 关键词检索 → 空返回（语义源兜底）
            return RetrievalResult(source_name=self.name, products=[], evidence=[])

        search_query = query.effective_query

        async def _do(sub_cat: str | None):
            try:
                return await akw(
                    search_query, query.top_k, query.category, sub_cat,
                    query.budget_max, query.budget_min,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug(f"keyword search failed: {e}")
                return []

        pairs = await _do(query.sub_category)
        if not pairs and query.sub_category:
            pairs = await _do(None)  # 子品类无结果 → 放宽

        results = [self._tr._product_to_result(p, score) for p, score in pairs]
        return RetrievalResult(source_name=self.name, products=results, evidence=[])
