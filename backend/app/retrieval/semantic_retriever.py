"""语义检索器 — Embedding + Qdrant ANN 搜索，替代 jieba 关键词检索。

检索流程:
1. embed(query) → 查询向量
2. Qdrant ANN → top_k * 2 候选
3. 约束过滤 (category, sub_category, price)
4. 返回 top_k

降级策略:
- Qdrant 不可用 → 本地缓存 embedding 做内存余弦相似度暴力搜索 (105 件商品毫秒级)
- Embedding API 不可用 → 抛出异常由上层处理
"""

import json
import logging
import math
from pathlib import Path
from typing import Optional

from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_SEARCH, USE_QDRANT, QDRANT_URL
from app.model_gateway.gateway import get_model_gateway

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).resolve().parent.parent.parent.parent / "backend" / "data" / "product_embeddings.json"
_CHUNK_CACHE_FILE = Path(__file__).resolve().parent.parent.parent.parent / "backend" / "data" / "product_chunk_embeddings.json"

# 内存缓存：本地 embedding 文件只加载一次
_local_cache: dict | None = None
_local_cache_loaded: bool = False
_local_chunk_cache: dict | None = None
_local_chunk_cache_loaded: bool = False


def _load_local_cache() -> dict:
    global _local_cache, _local_cache_loaded
    if _local_cache_loaded:
        return _local_cache or {}
    _local_cache_loaded = True
    if not _CACHE_FILE.exists():
        logger.warning(f"本地 embedding 缓存不存在: {_CACHE_FILE}，请先运行 scripts/index_products.py")
        return {}
    try:
        _local_cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        logger.info(f"加载本地 embedding 缓存: {_local_cache.get('count', 0)} 条")
        return _local_cache
    except Exception as e:
        logger.warning(f"加载本地 embedding 缓存失败: {e}")
        return {}


def _load_local_chunk_cache() -> dict:
    global _local_chunk_cache, _local_chunk_cache_loaded
    if _local_chunk_cache_loaded:
        return _local_chunk_cache or {}
    _local_chunk_cache_loaded = True
    if not _CHUNK_CACHE_FILE.exists():
        logger.warning(f"本地 chunk embedding 缓存不存在: {_CHUNK_CACHE_FILE}，请先运行 scripts/index_product_chunks.py")
        return {}
    try:
        _local_chunk_cache = json.loads(_CHUNK_CACHE_FILE.read_text(encoding="utf-8"))
        logger.info(f"加载本地 chunk embedding 缓存: {_local_chunk_cache.get('count', 0)} 条")
        return _local_chunk_cache
    except Exception as e:
        logger.warning(f"加载本地 chunk embedding 缓存失败: {e}")
        return {}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _reconstruct_chunk_text(chunk_type: str, chunk_index: int, product) -> str:
    """从 product.rag_knowledge 重建 chunk 原文（本地缓存降级时使用）。

    本地 product_chunk_embeddings.json 只存向量+元数据不存原文，
    Qdrant 可用时由其返回的 payload.text 提供原文。
    此函数作为降级场景的补齐手段，product 对象已在调用处获取。
    """
    rk = product.rag_knowledge
    if not rk:
        return ""
    try:
        if chunk_type == "summary":
            desc = (rk.marketing_description or "")[:200]
            return f"{product.title} {product.brand} {product.category} {product.sub_category} {desc}"
        elif chunk_type == "mkt":
            return (rk.marketing_description or "")[:300]
        elif chunk_type == "faq":
            faqs = rk.official_faq or []
            if chunk_index < len(faqs):
                faq = faqs[chunk_index]
                q = faq.question or ""
                a = faq.answer or ""
                return f"Q: {q} A: {a}"
        elif chunk_type == "rev":
            revs = rk.user_reviews or []
            if chunk_index < len(revs):
                rev = revs[chunk_index]
                nickname = rev.nickname or ""
                rating = rev.rating or 0
                content = rev.content or ""
                return f"[{nickname}][{rating}星] {content}"
    except Exception:
        pass
    return ""


class SemanticRetriever:
    """基于 Embedding 的语义检索器。"""

    def __init__(self, product_repo=None):
        self._repo = product_repo
        self._gateway = get_model_gateway()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[dict]:
        """语义检索 + Redis 缓存。"""
        cache_key = make_key("semantic_search", query, category or "", sub_category or "",
                             str(price_max or ""), str(price_min or ""), str(top_k))

        async def _do_search() -> list[dict]:
            return await self._search_impl(query, top_k, category, sub_category, price_max, price_min)

        return await cached(cache_key, REDIS_CACHE_TTL_SEARCH, _do_search)

    async def _search_impl(
        self,
        query: str,
        top_k: int,
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        # 1. Embed query
        try:
            embeddings = await self._gateway.embed([query], "text_embedding")
            query_vec = embeddings[0]
        except Exception as e:
            logger.error(f"Embedding API 调用失败: {e}")
            return await self._fallback_text_search(query, top_k, category, sub_category, price_max, price_min)

        # 2. 向量搜索
        candidates = await self._vector_search(query_vec, top_k * 3)

        # 3. 向量搜索无结果 → 回退文本搜索
        if not candidates:
            logger.info("向量搜索无结果，回退文本搜索")
            return await self._fallback_text_search(query, top_k, category, sub_category, price_max, price_min)

        # 4. 约束过滤
        candidates = self._apply_filters(candidates, category, sub_category, price_max, price_min)

        # 5. 返回 top_k
        return candidates[:top_k]

    async def _vector_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """Qdrant ANN → 降级本地余弦相似度"""
        if USE_QDRANT and QDRANT_URL:
            try:
                return self._qdrant_search(query_vec, top_k)
            except Exception as e:
                logger.warning(f"Qdrant 搜索失败，降级本地: {e}")

        return self._local_search(query_vec, top_k)

    def _qdrant_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        from qdrant_client import QdrantClient
        from app.core.config import QDRANT_COLLECTION_NAME

        client = QdrantClient(url=QDRANT_URL, timeout=10.0)
        results = client.query_points(
            collection_name=QDRANT_COLLECTION_NAME,
            query=query_vec,
            limit=top_k,
        )
        client.close()

        hits = []
        for hit in results.points:
            pid = hit.payload.get("product_id", "") if hit.payload else ""
            if not pid:
                continue
            product = self._repo.get_by_id(pid) if self._repo else None
            if product is None:
                continue
            hits.append(self._product_to_result(product, hit.score))
        return hits

    def _local_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """本地余弦相似度暴力搜索（105 件商品 < 10ms）"""
        cache = _load_local_cache()
        products_data = cache.get("products", [])
        if not products_data:
            return []

        scored = []
        for item in products_data:
            emb = item.get("embedding")
            if not emb or len(emb) != len(query_vec):
                continue
            sim = _cosine_similarity(query_vec, emb)
            pid = item.get("product_id", "")
            if sim > 0.0:
                scored.append((pid, sim))

        scored.sort(key=lambda x: x[1], reverse=True)

        hits = []
        for pid, score in scored[:top_k]:
            product = self._repo.get_by_id(pid) if self._repo else None
            if product is None:
                continue
            hits.append(self._product_to_result(product, score))
        return hits

    def _apply_filters(
        self,
        candidates: list[dict],
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        filtered = []
        for item in candidates:
            if category and item.get("category") != category:
                continue
            if sub_category and item.get("sub_category") != sub_category:
                continue
            price = item.get("price", 0)
            if price_max is not None and price > price_max:
                continue
            if price_min is not None and price < price_min:
                continue
            filtered.append(item)
        return filtered

    async def _fallback_text_search(
        self,
        query: str,
        top_k: int,
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        """Embedding API 挂了时的最后兜底：简单的子串匹配"""
        if not self._repo:
            return []

        try:
            candidates = self._repo.filter_by(category, sub_category, None, price_max, price_min)
        except Exception:
            candidates = self._repo.list_all() if hasattr(self._repo, 'list_all') else []

        if not candidates:
            return []

        query_lower = query.lower()
        scored = []
        for p in candidates:
            score = 0.0
            text = (p.title + " " + p.brand + " " + p.category + " " + p.sub_category).lower()
            for kw in query_lower.split():
                if len(kw) >= 2 and kw in text:
                    score += 1.0
            if score > 0:
                scored.append((p, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [self._product_to_result(p, s) for p, s in scored[:top_k]]

    # ---- Chunked Search ----

    async def search_chunked(
        self,
        query: str,
        top_k: int = 10,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
        aggregation: str = "max_score",
    ) -> list[dict]:
        """块级语义检索 → 聚合到产品级别。"""
        cache_key = make_key("chunk_search", query, str(top_k), category or "", sub_category or "",
                             str(price_max or ""), str(price_min or ""), aggregation)

        async def _do() -> list[dict]:
            return await self._chunk_search_impl(
                query, top_k, category, sub_category, price_max, price_min, aggregation,
            )

        return await cached(cache_key, REDIS_CACHE_TTL_SEARCH, _do)

    async def _chunk_search_impl(
        self,
        query: str,
        top_k: int,
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
        aggregation: str,
    ) -> list[dict]:
        # 1. Embed query
        try:
            embeddings = await self._gateway.embed([query], "text_embedding")
            query_vec = embeddings[0]
        except Exception as e:
            logger.error(f"Chunk search: Embedding API 调用失败: {e}")
            return await self._fallback_text_search(query, top_k, category, sub_category, price_max, price_min)

        # 2. 块级向量搜索 (检索 top_k * 10 个块)
        chunk_hits = await self._chunk_vector_search(query_vec, top_k * 10)

        # 3. 块级搜索无结果 → 降级旧产品级搜索
        if not chunk_hits:
            logger.info("Chunk search 无结果，降级产品级搜索")
            return await self._search_impl(query, top_k, category, sub_category, price_max, price_min)

        # 4. 约束过滤 (基于块的 payload)
        chunk_hits = self._apply_chunk_filters(chunk_hits, category, sub_category, price_max, price_min)

        # 4b. 约束过滤后无结果 → 降级产品级搜索
        if not chunk_hits:
            logger.info("Chunk 约束过滤后无结果，降级产品级搜索")
            return await self._search_impl(query, top_k, category, sub_category, price_max, price_min)

        # 5. 按 product_id 分组
        chunk_groups: dict[str, list[dict]] = {}
        for ch in chunk_hits:
            pid = ch["product_id"]
            if pid not in chunk_groups:
                chunk_groups[pid] = []
            chunk_groups[pid].append(ch)

        # 6. 聚合到产品级别
        ranked_pids = self._aggregate_chunks(chunk_groups, aggregation)[:top_k]

        # 7. 构建产品结果（复用 _product_to_result）
        results = []
        for pid, agg_score in ranked_pids:
            product = self._repo.get_by_id(pid) if self._repo else None
            if product is None:
                continue
            result = self._product_to_result(product, agg_score)
            # 附加匹配的块信息（含 payload 正文，供 evidence 内容提取）
            matched_chunks = chunk_groups.get(pid, [])
            result["matched_chunks"] = []
            for c in matched_chunks[:5]:
                payload = c.get("payload", {})
                chunk_text = payload.get("text", "")
                # 本地缓存降级时payload无text字段 → 从product.rag_knowledge重建
                if not chunk_text and product.rag_knowledge:
                    chunk_text = _reconstruct_chunk_text(
                        c["chunk_type"],
                        payload.get("chunk_index", 0),
                        product,
                    )
                result["matched_chunks"].append({
                    "chunk_type": c["chunk_type"],
                    "chunk_id": c["chunk_id"],
                    "score": c["score"],
                    "payload": {
                        "text": chunk_text,
                        "faq_question": payload.get("faq_question", ""),
                        "title": payload.get("title", ""),
                        "brand": payload.get("brand", ""),
                    },
                })
            result["matched_chunk_count"] = len(matched_chunks)
            results.append(result)

        # 8. 如果聚合后结果不足 top_k，用产品级搜索补齐
        if len(results) < top_k:
            fallback = await self._search_impl(query, top_k, category, sub_category, price_max, price_min)
            existing_ids = {r["product_id"] for r in results}
            for fb in fallback:
                if fb["product_id"] not in existing_ids:
                    fb.setdefault("matched_chunks", [])
                    fb.setdefault("matched_chunk_count", 0)
                    results.append(fb)
                    existing_ids.add(fb["product_id"])
                    if len(results) >= top_k:
                        break

        return results[:top_k]

    async def _chunk_vector_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """Qdrant/product_chunks ANN → 降级本地块缓存 → 降级产品级搜索"""
        if USE_QDRANT and QDRANT_URL:
            try:
                return self._qdrant_chunk_search(query_vec, top_k)
            except Exception as e:
                logger.warning(f"Qdrant chunk 搜索失败，降级本地: {e}")

        return self._local_chunk_search(query_vec, top_k)

    def _qdrant_chunk_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        from qdrant_client import QdrantClient
        from app.core.config import CHUNKED_COLLECTION_NAME

        client = QdrantClient(url=QDRANT_URL, timeout=10.0)
        results = client.query_points(
            collection_name=CHUNKED_COLLECTION_NAME,
            query=query_vec,
            limit=top_k,
            with_payload=True,
        )
        client.close()

        hits = []
        for hit in results.points:
            payload = hit.payload or {}
            pid = payload.get("product_id", "")
            if not pid:
                continue
            hits.append({
                "product_id": pid,
                "chunk_id": payload.get("chunk_id", ""),
                "chunk_type": payload.get("chunk_type", ""),
                "category": payload.get("category", ""),
                "sub_category": payload.get("sub_category", ""),
                "price": payload.get("price", 0),
                "score": hit.score,
                "payload": payload,
            })
        return hits

    def _local_chunk_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """本地块级余弦相似度暴力搜索。"""
        cache = _load_local_chunk_cache()
        chunks_data = cache.get("chunks", [])
        if not chunks_data:
            return []

        scored = []
        for item in chunks_data:
            emb = item.get("embedding")
            if not emb or len(emb) != len(query_vec):
                continue
            sim = _cosine_similarity(query_vec, emb)
            if sim > 0.0:
                payload = item.get("payload", {})
                scored.append({
                    "product_id": payload.get("product_id", ""),
                    "chunk_id": item.get("chunk_id", ""),
                    "chunk_type": item.get("chunk_type", ""),
                    "category": payload.get("category", ""),
                    "sub_category": payload.get("sub_category", ""),
                    "price": payload.get("price", 0),
                    "score": sim,
                    "payload": payload,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _apply_chunk_filters(
        self,
        chunks: list[dict],
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        filtered = []
        for ch in chunks:
            if category and ch.get("category") != category:
                continue
            if sub_category and ch.get("sub_category") != sub_category:
                continue
            price = ch.get("price", 0)
            if price_max is not None and price > price_max:
                continue
            if price_min is not None and price < price_min:
                continue
            filtered.append(ch)
        return filtered

    def _aggregate_chunks(
        self,
        chunk_groups: dict[str, list[dict]],
        aggregation: str = "max_score",
    ) -> list[tuple[str, float]]:
        """将块级得分聚合为产品级得分。"""
        # Chunk权重: summary(商品核心信息)和faq(精准匹配用户疑问)最高,
        # mkt(营销描述,有夸张可能)次之, rev(用户评论,噪音多情感偏差大)最低
        _WEIGHTS = {"summary": 1.0, "mkt": 0.9, "faq": 1.0, "rev": 0.8}

        product_scores = []
        for pid, chunks in chunk_groups.items():
            if aggregation == "max_score":
                score = max(c["score"] for c in chunks)
            elif aggregation == "weighted":
                weighted_sum = 0.0
                weight_total = 0.0
                for c in chunks:
                    w = _WEIGHTS.get(c.get("chunk_type", ""), 0.5)
                    if c["score"] > 0.4:
                        weighted_sum += c["score"] * w
                        weight_total += w
                score = weighted_sum / max(weight_total, 0.001) if weight_total > 0 else 0.0
            else:
                score = max(c["score"] for c in chunks)  # fallback to max_score

            product_scores.append((pid, round(score, 4)))

        product_scores.sort(key=lambda x: x[1], reverse=True)
        return product_scores

    def _product_to_result(self, product, score: float = 0.0) -> dict:
        evidence_ids = [f"E-MKT-{product.product_id}-0"]
        if product.rag_knowledge:
            for i in range(len(product.rag_knowledge.official_faq)):
                evidence_ids.append(f"POL-{product.product_id}-{i}")
            for i in range(len(product.rag_knowledge.user_reviews)):
                evidence_ids.append(f"R-{product.product_id}-{i}")

        return {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "sub_category": product.sub_category,
            "price": product.base_price,
            "image_urls": [self._repo.resolve_image_url(product.product_id)] if self._repo and hasattr(self._repo, 'resolve_image_url') else [],
            "skus": [s.model_dump() for s in product.skus],
            "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else None,
            "description": product.rag_knowledge.marketing_description if product.rag_knowledge else "",
            "score": round(score, 4),
            "evidence_ids": evidence_ids,
        }
