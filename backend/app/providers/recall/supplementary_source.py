"""补充证据召回源（stage=fallback）—— 平移自 ``retrieval_agent._supplementary_evidence_search``。

当主召回商品数不足（< ``query.min_results``）时触发：对 faq/rev 分块做 embedding 余弦
相似度反向发现被遗漏的商品（embedding 不可用时降级关键词子串匹配）。

注：原实现的 chunk 缓存路径存在多一级 ``backend/`` 的笔误（指向不存在的
``backend/backend/data``），导致该兜底长期空转。本次平移修正为正确的 ``backend/data``
（用 ``parents[3]`` 从 providers/recall 上溯到 backend）。该源仅在稀疏结果时触发，
修正后至多是「多召回若干兜底商品」的增益，不影响正常查询主链路。
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from app.framework.registry import component
from app.framework.retrieval.source import STAGE_FALLBACK, RecallSource
from app.framework.retrieval.types import RetrievalQuery, RetrievalResult

logger = logging.getLogger(__name__)

# providers/recall/supplementary_source.py -> parents[3] == backend/
_CHUNK_CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "product_chunk_embeddings.json"

_SIM_THRESHOLD = 0.35
_TOP_PIDS = 5


@component(kind="recall_source", name="supplementary", priority=30)
class SupplementaryRecallSource(RecallSource):
    """faq/rev 分块反向召回兜底源。"""

    name = "supplementary"
    priority = 30
    latency_budget_ms = 6000
    is_required = False
    stage = STAGE_FALLBACK

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        products: list[dict] = []
        evidence: list[dict] = []
        try:
            if not _CHUNK_CACHE_FILE.exists():
                return RetrievalResult(source_name=self.name)

            cache_data = json.loads(_CHUNK_CACHE_FILE.read_text(encoding="utf-8"))
            chunks = cache_data.get("chunks", [])
            evidence_chunks = [c for c in chunks if c.get("chunk_type") in ("faq", "rev")]
            if not evidence_chunks:
                return RetrievalResult(source_name=self.name)

            query_vec = await self._embed_query(query.query)
            matched_pids = self._match_pids(query, evidence_chunks, query_vec, cache_data.get("dimension", 1024))

            if matched_pids:
                products, evidence = self._build(query, evidence_chunks, matched_pids)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Supplementary evidence search skipped: %s", exc)

        return RetrievalResult(source_name=self.name, products=products, evidence=evidence)

    @staticmethod
    async def _embed_query(query_text: str) -> list[float] | None:
        try:
            from app.model_gateway.gateway import get_model_gateway

            gateway = get_model_gateway()
            # V6: 查询侧非对称编码（与主检索路径一致）
            embeddings = await gateway.embed([query_text], "text_embedding", is_query=True)
            return embeddings[0]
        except Exception:  # noqa: BLE001
            return None

    def _match_pids(
        self,
        query: RetrievalQuery,
        evidence_chunks: list[dict],
        query_vec: list[float] | None,
        dimension: int,
    ) -> dict[str, float]:
        matched: dict[str, float] = {}
        if query_vec and len(query_vec) == dimension:
            for chunk in evidence_chunks:
                emb = chunk.get("embedding")
                if not emb or len(emb) != len(query_vec):
                    continue
                # 上面已保证等长 → strict 冗余；不用 zip(strict=) 以兼容 py39 dev-import
                dot = sum(x * y for x, y in zip(query_vec, emb))  # noqa: B905
                mag_q = math.sqrt(sum(x * x for x in query_vec))
                mag_c = math.sqrt(sum(x * x for x in emb))
                sim = dot / (mag_q * mag_c) if mag_q > 0 and mag_c > 0 else 0.0
                if sim > _SIM_THRESHOLD:
                    pid = chunk.get("payload", {}).get("product_id", "")
                    if pid:
                        matched[pid] = max(matched.get(pid, 0), sim)
        else:
            # 降级：关键词子串匹配
            query_lower = query.query.lower()
            query_words = [w for w in query_lower.split() if len(w) >= 2]
            for chunk in evidence_chunks:
                payload = chunk.get("payload", {})
                text = (
                    f"{payload.get('title', '')} {payload.get('brand', '')} "
                    f"{payload.get('category', '')} {payload.get('sub_category', '')}"
                ).lower()
                score = sum(1.0 for w in query_words if w in text)
                if score > 0:
                    pid = payload.get("product_id", "")
                    if pid:
                        matched[pid] = max(matched.get(pid, 0), score)
        return matched

    @staticmethod
    def _build(
        query: RetrievalQuery,
        evidence_chunks: list[dict],
        matched_pids: dict[str, float],
    ) -> tuple[list[dict], list[dict]]:
        products: list[dict] = []
        evidence: list[dict] = []
        top_pids = sorted(matched_pids, key=matched_pids.get, reverse=True)[:_TOP_PIDS]
        for pid in top_pids:
            existing = {ep.get("product_id") for ep in products}
            for c in evidence_chunks:
                p = c.get("payload", {})
                if p.get("product_id") == pid and pid not in existing:
                    if query.category and p.get("category") != query.category:
                        continue
                    products.append(
                        {
                            "product_id": pid,
                            "title": p.get("title", ""),
                            "brand": p.get("brand", ""),
                            "category": p.get("category", ""),
                            "sub_category": p.get("sub_category", ""),
                            "price": p.get("price", 0),
                            "score": matched_pids.get(pid, 0),
                            "source_channel": "evidence_supplement",
                            "image_urls": [f"/api/products/{pid}/image"],
                            "rag_knowledge": {},
                            "skus": [],
                        }
                    )
                    break

            src_type = (
                "policy_faq"
                if any(
                    c.get("chunk_type") == "faq" and c.get("payload", {}).get("product_id") == pid
                    for c in evidence_chunks
                )
                else "review_positive"
            )
            evidence.append(
                {
                    "evidence_id": f"E-SUPP-{pid}",
                    "source_type": src_type,
                    "source_id": "supplementary_evidence",
                    "product_id": pid,
                    "content": f"Supplementary evidence match for: {query.query[:60]}",
                    "modality": "text",
                    "confidence": round(min(0.65, matched_pids.get(pid, 0.35)), 4),
                }
            )
        return products, evidence
