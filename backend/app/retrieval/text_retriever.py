import logging
import jieba

from app.core.config import DEFAULT_TOP_K
from app.repositories.product_repo import ProductRepository
from app.repositories.vector_repo import get_vector_repo
from app.model_gateway.gateway import get_model_gateway
from app.schemas.product import Product

logger = logging.getLogger(__name__)

# 查询中的停用词（对检索无贡献的虚词）
_QUERY_STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "一款", "一款", "推荐", "请", "帮", "想", "要", "买", "什么",
    "哪个", "哪种", "哪些", "怎么样", "如何", "给", "可以", "能", "能够",
    "有没有", "有没", "比较", "非常", "很", "太", "最", "更",
}


class TextRetriever:
    """V0 text retriever using official dataset's rag_knowledge for rich search."""

    def __init__(self, product_repo: ProductRepository | None = None):
        self._repo = product_repo or ProductRepository()

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[dict]:
        # First filter by constraints
        candidates = self._repo.filter_by(
            category=category,
            sub_category=sub_category,
            price_max=price_max,
            price_min=price_min,
        )

        if not candidates:
            return []

        # Score against full text (title + brand + marketing_description + faq + reviews)
        query_lower = query.lower()
        scored: list[tuple[Product, float]] = []

        for product in candidates:
            score = self._compute_rich_score(query_lower, product)
            if score > 0:
                scored.append((product, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            scored = [(p, 0.0) for p in candidates[:top_k]]

        top = scored[:top_k]

        results = []
        for product, score in top:
            # Collect evidence IDs from faq and reviews
            evidence_ids = [f"E-MKT-{product.product_id}"]
            if product.rag_knowledge:
                for i, faq in enumerate(product.rag_knowledge.official_faq):
                    evidence_ids.append(f"POL-{product.product_id}-{i}")
                for i, rev in enumerate(product.rag_knowledge.user_reviews):
                    evidence_ids.append(f"R-{product.product_id}-{i}")

            results.append({
                "product_id": product.product_id,
                "title": product.title,
                "brand": product.brand,
                "category": product.category,
                "sub_category": product.sub_category,
                "price": product.base_price,
                "image_urls": [self._repo.resolve_image_url(product.product_id)],
                "skus": [s.model_dump() for s in product.skus],
                "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else None,
                "description": product.rag_knowledge.marketing_description if product.rag_knowledge else "",
                "score": round(score, 4),
                "evidence_ids": evidence_ids,
            })

        return results

    def hybrid_search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[dict]:
        """混合检索：Qdrant 向量 + jieba 关键词 RRF 融合。

        Qdrant 不可用时透明降级为纯关键词搜索。
        """
        vector_repo = get_vector_repo()
        text_results = self.search(query, top_k * 2, category, sub_category, price_max, price_min)

        if not vector_repo.health_check():
            return text_results[:top_k]

        try:
            gateway = get_model_gateway()
            query_embedding = gateway.embed([query], "text_embedding")[0]
            vector_results = vector_repo.search_similar(query_embedding, top_k * 2)
        except Exception as e:
            logger.warning(f"向量搜索失败，降级为纯关键词: {e}")
            return text_results[:top_k]

        if not vector_results:
            return text_results[:top_k]

        # 为每个向量命中查找完整 Product
        vector_hits: list[dict] = []
        seen_ids: set[str] = set()
        for v in vector_results:
            pid = v.get("product_id", "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            product = self._repo.get_by_id(pid)
            if product is None:
                continue
            vector_hits.append(self._product_to_result(product, v["score"]))

        # RRF 融合
        merged = self._rrf_fusion(text_results, vector_hits, k=60)[:top_k]

        # 如果有约束过滤后的候选很多但没有向量命中，退回到纯文本
        if not merged:
            return text_results[:top_k]

        return merged

    @staticmethod
    def _rrf_fusion(
        results_a: list[dict],
        results_b: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion — 合并两个排序列表。"""
        scored: dict[str, tuple[dict, float]] = {}

        for rank, item in enumerate(results_a):
            pid = item["product_id"]
            rrf = 1.0 / (k + rank + 1)
            scored[pid] = (item, scored.get(pid, (item, 0.0))[1] + rrf)

        for rank, item in enumerate(results_b):
            pid = item["product_id"]
            rrf = 1.0 / (k + rank + 1)
            if pid in scored:
                existing = scored[pid][0]
                # 合并 evidence_ids
                merged_ids = list(set(existing.get("evidence_ids", []) + item.get("evidence_ids", [])))
                existing["evidence_ids"] = merged_ids
                existing["score"] = round(existing["score"] + rrf, 4)
                scored[pid] = (existing, scored[pid][1] + rrf)
            else:
                scored[pid] = (item, rrf)

        sorted_items = sorted(scored.values(), key=lambda x: x[1], reverse=True)
        return [item for item, _ in sorted_items]

    def _product_to_result(self, product: Product, score: float = 0.0) -> dict:
        evidence_ids = [f"E-MKT-{product.product_id}"]
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
            "image_urls": [self._repo.resolve_image_url(product.product_id)],
            "skus": [s.model_dump() for s in product.skus],
            "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else None,
            "description": product.rag_knowledge.marketing_description if product.rag_knowledge else "",
            "score": round(score, 4),
            "evidence_ids": evidence_ids,
        }

    def _compute_rich_score(self, query: str, product: Product) -> float:
        # 构建产品全文索引
        text_parts = [
            product.title,
            product.brand,
            product.category,
            product.sub_category,
        ]

        if product.rag_knowledge:
            rk = product.rag_knowledge
            text_parts.append(rk.marketing_description)
            for faq in rk.official_faq:
                text_parts.append(faq.question)
                text_parts.append(faq.answer)
            for rev in rk.user_reviews:
                text_parts.append(rev.content)

        full_text = " ".join(t.lower() for t in text_parts)
        title_lower = product.title.lower()

        # jieba 分词提取查询关键词（过滤停用词和单字）
        keywords = [w.strip() for w in jieba.cut(query) if len(w.strip()) >= 2 and w.strip() not in _QUERY_STOP_WORDS]

        if not keywords:
            keywords = [query]

        score = 0.0

        for kw in keywords:
            kw_lower = kw.lower()
            count = full_text.count(kw_lower)
            if count > 0:
                # 在产品全文中的命中次数
                score += min(count, 10) * 0.8

            # 标题命中额外加分
            title_count = title_lower.count(kw_lower)
            if title_count > 0:
                score += title_count * 2.0

            # 品类/子类精确匹配高分
            if kw_lower in product.category or kw_lower in product.sub_category:
                score += 5.0

        return score
