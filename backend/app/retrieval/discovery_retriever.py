"""Structured candidate discovery for the v8 catalog index.

Facts determine eligibility; vector similarity only orders or supplements
eligible candidates.  This is intentionally not a replacement for the legacy
retriever until the v8 collection is populated and shadow-validated.
"""

from __future__ import annotations

import logging

from app.core.config import DISCOVERY_COLLECTION_NAME, QDRANT_URL, USE_DISCOVERY_V8, USE_QDRANT
from app.model_gateway.gateway import get_model_gateway
from app.repositories.product_fact_repo import ProductFactRepository
from app.services.product_facts import (
    extract_product_facts,
    filter_products_by_facts,
    food_constraint_groups,
)

logger = logging.getLogger(__name__)


class DiscoveryRetriever:
    def __init__(self, product_repo):
        self._repo = product_repo
        self._fact_repo = ProductFactRepository()
        self._gateway = get_model_gateway()

    @staticmethod
    def _item(product, score: float = 0.0, facts: list[dict] | None = None) -> dict:
        facts = facts if facts is not None else [f.model_payload() for f in extract_product_facts(product)]
        return {
            "product_id": product.product_id, "title": product.title, "brand": product.brand,
            "category": product.category, "sub_category": product.sub_category,
            "price": float(product.base_price), "relevance_score": score,
            "discovery_source": "structured_facts",
            "product_facts": facts,
            # 所有消费端都通过统一图片端点读取，避免数据集相对路径在 Web/Android
            # 环境下失效并造成“检索卡片没有图”。
            "image_urls": [f"/api/products/{product.product_id}/image"],
            "skus": [sku.model_dump() if hasattr(sku, "model_dump") else sku for sku in (product.skus or [])],
            "rag_knowledge": product.rag_knowledge.model_dump() if getattr(product, "rag_knowledge", None) else {},
            "description": getattr(getattr(product, "rag_knowledge", None), "marketing_description", "") or "",
        }

    async def search(self, query: str, category: str | None = None,
                     budget_max: float | None = None, top_k: int = 12,
                     must_tags: list[str] | None = None) -> tuple[list[dict], dict]:
        products = self._repo.list_all()
        # Nutrition constraints are meaningful only for food/drink.  Do not let
        # unrelated products survive simply because they lack a nutrition field.
        food_constrained = bool(food_constraint_groups(query, must_tags)) or any(
            term in (query or "") for term in ("不想长胖", "控卡", "轻负担", "减脂")
        )
        if food_constrained and not category:
            products = [p for p in products if p.category == "食品饮料"]
        if category:
            products = [p for p in products if p.category == category]
        if budget_max is not None:
            products = [p for p in products if float(p.base_price) <= budget_max]
        products, report = filter_products_by_facts(products, query, must_tags)
        persisted_facts = await self._fact_repo.facts_for_products([p.product_id for p in products])
        if persisted_facts is not None:
            # A deployed fact table wins over regenerated values.  Rows missing
            # the required catalog fact cannot pass a hard nutrition condition.
            required = [set(group) for group in report.get("required", [])]
            light = bool(report.get("light_request"))
            light_keys = {
                "nutrition.zero_sugar", "nutrition.low_sugar", "nutrition.zero_fat",
                "nutrition.low_fat", "nutrition.zero_calorie", "nutrition.low_calorie",
                "nutrition.high_protein",
            }
            if report.get("applied"):
                scoped = []
                for product in products:
                    keys = {f.get("fact_key", "") for f in persisted_facts.get(product.product_id, [])}
                    if all(keys & alternatives for alternatives in required) and (not light or bool(keys & light_keys)):
                        scoped.append(product)
                products = scoped
                report = dict(report, matched=len(products), fact_source="postgres")
            else:
                report = dict(report, fact_source="postgres")
        # A fact-filtered list is useful even before the new collection is built.
        if not products:
            return [], report
        if not (USE_DISCOVERY_V8 and USE_QDRANT and QDRANT_URL):
            return [self._item(p, facts=(persisted_facts or {}).get(p.product_id)) for p in products[:top_k]], report
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, Range

            vector = (await self._gateway.embed([query], "text_embedding", is_query=True))[0]
            allowed = [p.product_id for p in products]
            conditions = [FieldCondition(key="product_id", match=MatchAny(any=allowed))]
            if category:
                conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))
            if budget_max is not None:
                conditions.append(FieldCondition(key="price", range=Range(lte=budget_max)))
            client = QdrantClient(url=QDRANT_URL, timeout=8.0)
            try:
                result = client.query_points(DISCOVERY_COLLECTION_NAME, query=vector, using="dense",
                                             query_filter=Filter(must=conditions), limit=top_k,
                                             with_payload=True)
            except Exception:
                result = client.query_points(DISCOVERY_COLLECTION_NAME, query=vector,
                                             query_filter=Filter(must=conditions), limit=top_k,
                                             with_payload=True)
            finally:
                client.close()
            by_id = {p.product_id: p for p in products}
            ranked = [self._item(by_id[h.payload["product_id"]], float(h.score),
                                 (persisted_facts or {}).get(h.payload["product_id"])) for h in result.points
                      if h.payload and h.payload.get("product_id") in by_id]
            if ranked:
                for item in ranked:
                    item["discovery_source"] = "v8_dense"
                return ranked, report
        except Exception as exc:  # v8 shadow index must never break production retrieval
            logger.info("v8 discovery unavailable; using fact candidates: %s", exc)
        return [self._item(p, facts=(persisted_facts or {}).get(p.product_id)) for p in products[:top_k]], report
