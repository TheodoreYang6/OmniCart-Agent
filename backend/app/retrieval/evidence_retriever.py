"""Retrieve supporting evidence only after products have been selected.

The v8 evidence collection is intentionally incapable of introducing a new
product candidate. It can only explain IDs passed in by the discovery layer,
which prevents a highly similar review from hijacking a recommendation.
"""

from __future__ import annotations

import logging

from app.core.config import EVIDENCE_COLLECTION_NAME, QDRANT_URL, USE_DISCOVERY_V8, USE_QDRANT
from app.model_gateway.gateway import get_model_gateway

logger = logging.getLogger(__name__)


class EvidenceRetriever:
    def __init__(self) -> None:
        self._gateway = get_model_gateway()

    async def search(self, query: str, product_ids: list[str], *, max_per_product: int = 2) -> list[dict]:
        product_ids = list(dict.fromkeys(str(pid) for pid in product_ids if pid))
        if not product_ids or not (USE_DISCOVERY_V8 and USE_QDRANT and QDRANT_URL):
            return []
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            vector = (await self._gateway.embed([query], "text_embedding", is_query=True))[0]
            client = QdrantClient(url=QDRANT_URL, timeout=8.0)
            try:
                evidence: list[dict] = []
                # Query product-by-product to guarantee evidence diversity: a
                # popular product must not consume every global top-K slot.
                for pid in product_ids:
                    result = client.query_points(
                        EVIDENCE_COLLECTION_NAME, query=vector, using="dense",
                        query_filter=Filter(must=[FieldCondition(key="product_id", match=MatchValue(value=pid))]),
                        limit=max_per_product, with_payload=True,
                    )
                    for hit in result.points:
                        payload = hit.payload or {}
                        content = str(payload.get("content", "")).strip()
                        if not content:
                            continue
                        evidence.append({
                            "evidence_id": str(hit.id), "product_id": pid,
                            "source_type": str(payload.get("source_type", "catalog")),
                            "modality": "text", "content": content[:500],
                            "confidence": max(0.0, min(1.0, float(hit.score))),
                            "evidence_source": "v8_evidence",
                        })
                return evidence
            finally:
                client.close()
        except Exception as exc:  # evidence is additive, never a retrieval failure
            logger.info("v8 evidence unavailable; keeping legacy evidence: %s", exc)
            return []
