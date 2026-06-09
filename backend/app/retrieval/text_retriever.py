"""文本检索器 — 基于 Embedding 语义搜索 (已移除 jieba)。

V2 重构: 用 SemanticRetriever (Qwen Embedding + Qdrant ANN) 替代 jieba 关键词检索。
保留 hybrid_search 作为 Qdrant 向量 + RRF 融合的增强模式。
"""

import logging

from app.core.config import DEFAULT_TOP_K, REDIS_CACHE_TTL_SEARCH
from app.core.cache import cached, make_key
from app.repositories.product_repo import ProductRepository
from app.repositories.vector_repo import get_vector_repo
from app.model_gateway.gateway import get_model_gateway
from app.retrieval.semantic_retriever import SemanticRetriever
from app.schemas.product import Product

logger = logging.getLogger(__name__)


class TextRetriever:
    """语义文本检索器 — Embedding + Qdrant ANN (V2 重构: 不再使用 jieba)。"""

    def __init__(self, product_repo: ProductRepository | None = None):
        self._repo = product_repo or ProductRepository()
        self._semantic = SemanticRetriever(self._repo)

    async def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[dict]:
        """语义检索 + Redis 缓存。"""
        cache_key = make_key("search", query, category or "", sub_category or "",
                             str(price_max or ""), str(price_min or ""), str(top_k))

        async def _do_search() -> list[dict]:
            return await self._search_async(query, top_k, category, sub_category, price_max, price_min)

        return await cached(cache_key, REDIS_CACHE_TTL_SEARCH, _do_search)

    async def _search_async(
        self, query: str, top_k: int = DEFAULT_TOP_K,
        category: str | None = None, sub_category: str | None = None,
        price_max: float | None = None, price_min: float | None = None,
    ) -> list[dict]:
        """异步语义检索 — 委托给 SemanticRetriever。"""
        return await self._semantic.search(query, top_k, category, sub_category, price_max, price_min)

    async def search_chunked(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
        aggregation: str = "max_score",
    ) -> list[dict]:
        """块级语义检索 + 产品聚合。"""
        return await self._semantic.search_chunked(
            query, top_k, category, sub_category, price_max, price_min, aggregation,
        )

    def _search_sync(
        self, query: str, top_k: int = DEFAULT_TOP_K,
        category: str | None = None, sub_category: str | None = None,
        price_max: float | None = None, price_min: float | None = None,
    ) -> list[dict]:
        """同步检索 — 降级使用 filter_by + 简单匹配 (不再使用 jieba)。"""
        candidates = self._repo.filter_by(category, sub_category, None, price_max, price_min)
        if not candidates:
            return []

        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) >= 2]
        if not query_words:
            query_words = [query_lower]

        scored: list[tuple[Product, float]] = []
        for product in candidates:
            text = (product.title + " " + product.brand + " " +
                    product.category + " " + product.sub_category).lower()
            if product.rag_knowledge:
                text += " " + product.rag_knowledge.marketing_description.lower()
            score = sum(1.0 for w in query_words if w in text)
            if score > 0:
                scored.append((product, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            scored = [(p, 0.0) for p in candidates[:top_k]]

        results = []
        for product, score in scored[:top_k]:
            results.append(self._product_to_result(product, score))
        return results

    def _product_to_result(self, product: Product, score: float = 0.0) -> dict:
        evidence_ids = [f"E-MKT-{product.product_id}-0"]
        if product.rag_knowledge:
            for i, faq in enumerate(product.rag_knowledge.official_faq):
                evidence_ids.append(f"POL-{product.product_id}-{i}")
            for i, rev in enumerate(product.rag_knowledge.user_reviews):
                evidence_ids.append(f"R-{product.product_id}-{i}")

        return {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "sub_category": product.sub_category,
            "price": product.base_price,
            "image_urls": [self._repo.resolve_image_url(product.product_id)] if hasattr(self._repo, 'resolve_image_url') else [],
            "skus": [s.model_dump() for s in product.skus],
            "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else None,
            "description": product.rag_knowledge.marketing_description if product.rag_knowledge else "",
            "score": round(score, 4),
            "evidence_ids": evidence_ids,
        }
