"""V9：shopping.search 每次工具调用独立使用的多视角 Chunk 检索器。"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any

from app.core.cache import cached, make_key
from app.core.config import (QDRANT_URL, REDIS_CACHE_TTL_SEARCH, USE_QDRANT,
                             V9_CHUNK_COLLECTION_NAME, V9_RERANK_TIMEOUT)
from app.model_gateway.gateway import get_model_gateway
from app.providers.recall.rerank_fusion import RerankFusion
from app.repositories.product_repo import get_product_repo
from app.services.candidate_llm_filter import CandidateLLMFilter, plan_snapshot
from app.services.product_facts import extract_product_facts

logger = logging.getLogger(__name__)
_CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "product_chunk_embeddings_v9.json"
_V9_SPARSE_STATS = Path(__file__).resolve().parents[2] / "data" / "bm25_stats_v9.json"
_ENTITY_RE = re.compile(r"(?:[A-Za-z]+[\w-]*\d[\w-]*|\d+[A-Za-z][\w-]*|\b\d+(?:gb|tb|mah|ml|kg|g)\b)", re.I)


def _plan_value(plan: Any, name: str, default: Any = None) -> Any:
    return plan.get(name, default) if isinstance(plan, dict) else getattr(plan, name, default)


def _filters(plan: Any, constraints: Any) -> dict[str, Any]:
    def value(obj: Any, field: str):
        return obj.get(field) if isinstance(obj, dict) else getattr(obj, field, None)
    return {"category": value(constraints, "category") or _plan_value(plan, "category"),
            "sub_category": value(constraints, "sub_category") or _plan_value(plan, "sub_category"),
            "price_max": value(constraints, "budget_max") or _plan_value(plan, "budget_hint"),
            "price_min": value(constraints, "budget_min")}


def _explicit_terms(query: str, plan: Any) -> bool:
    terms = _plan_value(plan, "entity_terms", []) or []
    return bool(terms or _ENTITY_RE.search(query) or re.search(r"(?:苹果|华为|小米|索尼|iphone|ipad|airpods)", query, re.I))


def _qdrant_filter(filters: dict):
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, Range
    must = []
    if filters.get("category"):
        must.append(FieldCondition(key="category", match=MatchValue(value=filters["category"])))
    if filters.get("sub_category"):
        sub = filters["sub_category"]
        must.append(FieldCondition(key="sub_category", match=(MatchAny(any=list(sub)) if isinstance(sub, (list, tuple, set)) else MatchValue(value=sub))))
    if filters.get("price_max") is not None or filters.get("price_min") is not None:
        must.append(FieldCondition(key="price", range=Range(gte=filters.get("price_min"), lte=filters.get("price_max"))))
    return Filter(must=must) if must else None


class ToolChunkRetrieverV9:
    """一次 search 调用 = 一次 embedding + top100 chunk + 商品聚合 + rerank/filter。"""

    def __init__(self, repo=None, gateway=None, filterer=None):
        self._repo = repo or get_product_repo()
        self._gateway = gateway or get_model_gateway()
        self._filterer = filterer or CandidateLLMFilter()
        self._reranker = RerankFusion(self._gateway)

    @staticmethod
    def signature(query: str, plan: Any, constraints: Any, intent: str) -> str:
        snapshot = plan_snapshot(plan, constraints)
        snapshot["intent"] = intent or snapshot["intent"]
        # v4：卡片图片地址成为 V9 商品契约的一部分。旧缓存只含 image_path，SSE
        # 白名单会丢弃该字段，因而必须与旧结果隔离，不能让用户继续看到无图卡片。
        return make_key("v9_tool_search", "v4", query.strip(), json.dumps(snapshot, ensure_ascii=False, sort_keys=True))

    async def search(self, *, query: str, plan: Any, constraints: Any, intent: str = "recommend",
                     top_k: int = 5) -> dict[str, Any]:
        signature = self.signature(query, plan, constraints, intent)

        async def _execute() -> dict[str, Any]:
            return await self._search_once(query, plan, constraints, intent, top_k, signature)

        # 签名包含 query、Router 子目标和所有过滤条件。相同调用不重复 embedding/Qdrant；
        # 不同深度思考子目标必然得到独立快照。
        return await cached(signature, REDIS_CACHE_TTL_SEARCH, _execute)

    async def _search_once(self, query: str, plan: Any, constraints: Any, intent: str,
                           top_k: int, signature: str) -> dict[str, Any]:
        started = time.perf_counter()
        vector = (await self._gateway.embed([query], "text_embedding", is_query=True))[0]
        filters = self._validated_filters(_filters(plan, constraints))
        dimension_mismatch = not self._vector_dimension_matches(vector)
        if dimension_mismatch:
            # 不允许把 128 维查询截断后和 1024 维旧索引相乘：那会得到看似有分、
            # 实则随机的召回。明确走可解释的词面保底，并把问题留在日志与返回 trace。
            logger.error("v9 embedding/index dimension mismatch; using lexical fallback")
            hits = self._lexical_hits(query, filters)
        else:
            hits = await asyncio.to_thread(self._query_chunks, vector, query, filters, _explicit_terms(query, plan))
        candidates = self._aggregate(hits, filters)
        # 本地 rerank 是压缩层，不可用时沿聚合顺序继续。每次只处理 24 件的紧凑文档。
        reranked = await self._rerank(query, candidates[:24])
        # 证据从本次命中的 chunk 快照直接整理，与 Filter 并行；绝不为证据再做一次
        # query embedding 或 Qdrant 搜索。
        evidence_task = asyncio.create_task(asyncio.to_thread(
            lambda: {p["product_id"]: self._evidence(p) for p in reranked[:12] if p.get("product_id")}))
        filter_result, all_evidence = await asyncio.gather(
            self._filterer.filter(query=query, plan={**plan_snapshot(plan, constraints), "intent": intent},
                                  constraints=constraints, candidates=reranked[:12]),
            evidence_task,
        )
        final = self._apply_filter(reranked[:12], filter_result, top_k)
        evidence_pack = {p["product_id"]: all_evidence.get(p["product_id"], [])
                         for p in final if p.get("product_id")}
        elapsed = round((time.perf_counter() - started) * 1000)
        return {"signature": signature, "query": query, "filters": filters, "intent": intent,
                "chunk_hits": len(hits), "aggregated_count": len(candidates), "reranked_count": len(reranked[:12]),
                "products": final, "filter": filter_result, "evidence_pack": evidence_pack,
                "latency_ms": elapsed, "source": "v9_lexical_dimension_fallback" if dimension_mismatch else "v9",
                "dimension_mismatch": dimension_mismatch}

    def _validated_filters(self, filters: dict) -> dict:
        """只把可验证的二级品类下推为 Qdrant 精确过滤。

        Router 的“蓝牙耳机 / 面膜 / 通勤鞋”常是用户自然语言，不一定等于商品库的
        标准 ``sub_category``（例如库内是“真无线耳机”）。把这种近义词作为 exact
        filter 会得到 0 个 chunk；它应继续参与向量、rerank 与 LLM Filter，而非被
        静默当成硬约束。
        """
        normalized = dict(filters)
        requested = normalized.get("sub_category")
        if not requested:
            return normalized
        try:
            valid = set(self._repo.get_sub_categories(normalized.get("category")) or [])
        except Exception as exc:
            logger.debug("v9 sub-category validation unavailable: %s", exc)
            return normalized
        values = list(requested) if isinstance(requested, (list, tuple, set)) else [requested]
        accepted = [value for value in values if value in valid]
        if not accepted:
            normalized["sub_category"] = None
        else:
            normalized["sub_category"] = accepted if isinstance(requested, (list, tuple, set)) else accepted[0]
        return normalized

    @staticmethod
    def _vector_size(config: Any) -> int | None:
        """兼容 Qdrant 的单向量与命名向量配置，读取 dense 的维度。"""
        if isinstance(config, dict):
            dense = config.get("dense")
            return int(getattr(dense, "size", 0) or 0) or None
        return int(getattr(config, "size", 0) or 0) or None

    def _vector_dimension_matches(self, vector: list[float]) -> bool:
        actual = len(vector or [])
        if not actual:
            return False
        expected: int | None = None
        if USE_QDRANT and QDRANT_URL:
            try:
                from app.core.qdrant_client import get_qdrant

                client = get_qdrant()
                if client is not None:
                    expected = self._vector_size(client.get_collection(V9_CHUNK_COLLECTION_NAME).config.params.vectors)
            except Exception as exc:  # 集合不可用时由本地缓存继续承接
                logger.debug("v9 collection dimension unavailable: %s", exc)
        if expected is None:
            try:
                expected = int(json.loads(_CACHE_FILE.read_text(encoding="utf-8")).get("dimension") or 0) or None
            except Exception:
                pass
        return expected is None or expected == actual

    def _lexical_hits(self, query: str, filters: dict) -> list[dict]:
        """维度异常时的安全保底：只用商品身份/标题词面召回，不伪造向量相似度。"""
        try:
            products = self._repo.search_text(query, top_k=100)
        except Exception as exc:
            logger.warning("v9 lexical fallback failed: %s", exc)
            return []
        hits: list[dict] = []
        for product in products:
            if filters.get("category") and product.category != filters["category"]:
                continue
            if filters.get("sub_category") and product.sub_category != filters["sub_category"]:
                continue
            if filters.get("price_max") is not None and float(product.base_price) > float(filters["price_max"]):
                continue
            if filters.get("price_min") is not None and float(product.base_price) < float(filters["price_min"]):
                continue
            text = f"[商品] {product.brand} {product.title} {product.category} {product.sub_category}"
            hits.append({"product_id": product.product_id, "score": 1.0 - len(hits) * 0.001,
                         "payload": {"product_id": product.product_id, "chunk_type": "identity", "text": text},
                         "chunk_type": "identity"})
        return hits

    def _query_chunks(self, vector: list[float], query: str, filters: dict, hybrid: bool) -> list[dict]:
        if USE_QDRANT and QDRANT_URL:
            try:
                from app.core.qdrant_client import get_qdrant
                from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector
                client = get_qdrant()
                if client is not None:
                    qfilter = _qdrant_filter(filters)
                    if hybrid:
                        try:
                            from app.retrieval.sparse_encoder import encode_query, load_stats
                            sparse = encode_query(query, load_stats(_V9_SPARSE_STATS))
                            if sparse[0]:
                                result = client.query_points(
                                    collection_name=V9_CHUNK_COLLECTION_NAME,
                                    prefetch=[Prefetch(query=vector, using="dense", limit=100, filter=qfilter),
                                              Prefetch(query=SparseVector(indices=sparse[0], values=sparse[1]), using="bm25", limit=100, filter=qfilter)],
                                    query=FusionQuery(fusion=Fusion.RRF), limit=100, with_payload=True)
                                return self._hits(result)
                        except Exception as exc:
                            logger.info("v9 hybrid unavailable, dense only: %s", exc)
                    result = client.query_points(collection_name=V9_CHUNK_COLLECTION_NAME, query=vector,
                                                 using="dense", limit=100, query_filter=qfilter, with_payload=True)
                    return self._hits(result)
            except Exception as exc:
                logger.warning("v9 Qdrant query failed: %s", exc)
        return self._local_hits(vector, filters)

    @staticmethod
    def _hits(result: Any) -> list[dict]:
        out = []
        for hit in getattr(result, "points", []) or []:
            payload = hit.payload or {}
            if payload.get("product_id"):
                out.append({"product_id": payload["product_id"], "score": float(hit.score), "payload": payload,
                            "chunk_type": payload.get("chunk_type", "")})
        return out

    def _local_hits(self, vector: list[float], filters: dict) -> list[dict]:
        try:
            cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
        out = []
        for item in cache.get("chunks", []):
            payload = item.get("payload", {})
            if filters.get("category") and payload.get("category") != filters["category"]:
                continue
            if filters.get("price_max") is not None and float(payload.get("price", 0)) > float(filters["price_max"]):
                continue
            emb = item.get("embedding", [])
            denom = math.sqrt(sum(x*x for x in vector)) * math.sqrt(sum(x*x for x in emb))
            if denom:
                out.append({"product_id": payload.get("product_id"), "score": sum(a*b for a, b in zip(vector, emb)) / denom,
                            "payload": payload, "chunk_type": payload.get("chunk_type", "")})
        return sorted(out, key=lambda item: -item["score"])[:100]

    def _aggregate(self, hits: list[dict], filters: dict) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for hit in hits:
            grouped.setdefault(str(hit["product_id"]), []).append(hit)
        candidates = []
        weights = {"identity": 1.25, "facts": 1.15, "marketing": 1.0, "faq": 0.92,
                   "review_aspect": 0.72, "review": 0.50}
        for pid, product_hits in grouped.items():
            product = self._repo.get_by_id(pid)
            if not product:
                continue
            # 强约束仅由 Qdrant payload（品类、预算）收窄；事实留待 filter/Guard，绝不前截断。
            per_type: dict[str, float] = {}
            for hit in product_hits:
                typ = str(hit.get("chunk_type", ""))
                per_type[typ] = max(per_type.get(typ, -1.0), float(hit["score"]))
            identity_support = max(per_type.get("identity", -1.0), per_type.get("facts", -1.0), per_type.get("marketing", -1.0), per_type.get("faq", -1.0))
            score = sum(weights.get(typ, 0.45) * value for typ, value in per_type.items())
            score += 0.025 * max(0, len(per_type) - 1)
            if identity_support < 0:  # 评论独自命中绝不能压过有身份/规格支持的商品
                score *= 0.55
            matched = sorted(product_hits, key=lambda item: -item["score"])
            selected, seen_types = [], set()
            for hit in matched:
                typ = hit.get("chunk_type", "")
                if typ not in seen_types or len(selected) < 3:
                    selected.append(hit)
                    seen_types.add(typ)
                if len(selected) >= 6:
                    break
            facts = [fact.model_payload() for fact in extract_product_facts(product)]
            candidates.append({"product_id": product.product_id, "title": product.title, "brand": product.brand,
                               "category": product.category, "sub_category": product.sub_category,
                               "price": product.base_price, "image_path": product.image_path,
                               # 商品卡消费的是 API 图片地址而不是数据集内部路径。V9 曾只
                               # 保留 image_path，随后 SSE 白名单会将它剔除，导致所有由
                               # V9 召回的推荐卡都拿不到图片。这里在商品聚合边界统一补全。
                               # 统一走稳定图片 API；端点内部处理原图缺失与占位，不能
                               # 把数据集的 image_path 完整性变成推荐卡是否有图的前提。
                               "image_urls": [f"/api/products/{product.product_id}/image"],
                               "skus": [sku.model_dump() for sku in product.skus],
                               "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else {},
                               "description": product.rag_knowledge.marketing_description if product.rag_knowledge else "",
                               "product_facts": facts, "matched_chunks": selected,
                               "chunk_aggregate_score": round(score, 5), "chunk_type_support": sorted(per_type)})
        return sorted(candidates, key=lambda item: -item["chunk_aggregate_score"])[:24]

    async def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        if len(candidates) < 2:
            return candidates
        evidence = [dict(product_id=p["product_id"], source_type="chunk", content=(h.get("payload") or {}).get("text", ""))
                    for p in candidates for h in (p.get("matched_chunks") or [])]
        try:
            return (await asyncio.wait_for(self._reranker.rerank(query=query, products=candidates, evidence=evidence),
                                           timeout=V9_RERANK_TIMEOUT))[:12]
        except Exception as exc:
            logger.info("v9 rerank skipped: %s", exc)
            for p in candidates:
                p.setdefault("relevance_score", p.get("chunk_aggregate_score", 0))
            return candidates[:12]

    @staticmethod
    def _apply_filter(candidates: list[dict], result: dict, top_k: int) -> list[dict]:
        by_id = {str(p.get("product_id")): p for p in candidates}
        ordered: list[dict] = []
        for bucket, limit in (("primary", 3), ("alternative", 6), ("conditional", 6)):
            for entry in (result.get(bucket) or [])[:limit]:
                pid = str(entry.get("product_id") or "")
                product = by_id.get(pid)
                if product and product not in ordered:
                    product = dict(product)
                    product["filter_bucket"] = bucket
                    product["card_reason"] = str(entry.get("reason") or "")
                    product["evidence_types"] = entry.get("evidence_types") or []
                    ordered.append(product)
        if ordered:
            return ordered[:max(1, min(9, top_k if top_k else 5))]
        # ``missing_group`` is an explicit closed-set judgement: none of the
        # candidates satisfies the request.  Returning the pre-filter list here
        # previously showed speakers/scales/power banks for a headphone query.
        # Only invalid/model-unavailable filters may deterministically fall back.
        if str(result.get("missing_group") or "").strip() and result.get("status") == "model":
            return []
        return candidates[:max(1, top_k)]

    @staticmethod
    def _evidence(product: dict) -> list[dict]:
        out = []
        for hit in product.get("matched_chunks") or []:
            payload = hit.get("payload") or {}
            out.append({"evidence_id": f"v9:{payload.get('chunk_id', '')}", "product_id": product.get("product_id"),
                        "source_type": payload.get("source_type", payload.get("chunk_type", "")),
                        "content": payload.get("text", "")[:320], "source_ref": payload.get("source_ref", ""),
                        "confidence": float(hit.get("score", 0) or 0)})
        return out
