"""证据增强召回源（stage=enrich）—— 平移自 ``_review_channel`` / ``_policy_channel``。

这两个源不做检索，而是读取 ``query.seed_products``（已召回商品）二次挖掘证据：
- ReviewRecallSource：从 user_reviews 按评分产出 review_risk / review_neutral / review_positive。
- PolicyRecallSource：从 official_faq 产出 policy_faq（仅取 top 3 商品）。
"""

from __future__ import annotations

from app.framework.registry import component
from app.framework.retrieval.source import STAGE_ENRICH, RecallSource
from app.framework.retrieval.types import RetrievalQuery, RetrievalResult


def _reviews_of(rk: object) -> list:
    if isinstance(rk, dict):
        return rk.get("user_reviews", []) or []
    return list(getattr(rk, "user_reviews", []) or [])


def _faqs_of(rk: object) -> list:
    if isinstance(rk, dict):
        return rk.get("official_faq", []) or []
    return list(getattr(rk, "official_faq", []) or [])


def _rget(obj: object, key: str, default: object) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@component(kind="recall_source", name="review", priority=40)
class ReviewRecallSource(RecallSource):
    """评论证据挖掘源。"""

    name = "review"
    priority = 40
    latency_budget_ms = 2000
    is_required = False
    stage = STAGE_ENRICH

    def should_activate(self, query: RetrievalQuery) -> bool:
        channels = query.metadata.get("channels")
        if channels is None:
            return True
        return "review" in channels

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        evidence: list[dict] = []
        for item in query.seed_products or []:
            pid = item.get("product_id", "")
            rk = item.get("rag_knowledge")
            if not pid or not rk:
                continue
            for i, review in enumerate(_reviews_of(rk)):
                rating = _rget(review, "rating", 3)
                nickname = _rget(review, "nickname", "")
                content = _rget(review, "content", "")
                if rating <= 2:
                    source_type, confidence = "review_risk", 0.8 if rating == 1 else 0.5
                elif rating == 3:
                    source_type, confidence = "review_neutral", 0.4
                else:
                    source_type, confidence = "review_positive", 0.7
                evidence.append(
                    {
                        "evidence_id": f"R-{pid}-{i}",
                        "source_type": source_type,
                        "source_id": pid,
                        "product_id": pid,
                        "content": f"[{nickname}][{rating}星] {str(content)[:150]}",
                        "modality": "text",
                        "confidence": confidence,
                    }
                )
        return RetrievalResult(source_name=self.name, evidence=evidence)


@component(kind="recall_source", name="policy", priority=50)
class PolicyRecallSource(RecallSource):
    """政策/FAQ 证据挖掘源（取 top 3 商品）。"""

    name = "policy"
    priority = 50
    latency_budget_ms = 2000
    is_required = False
    stage = STAGE_ENRICH

    def should_activate(self, query: RetrievalQuery) -> bool:
        channels = query.metadata.get("channels")
        if channels is None:
            return True
        return "policy" in channels

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        evidence: list[dict] = []
        for item in (query.seed_products or [])[:3]:
            pid = item.get("product_id", "")
            rk = item.get("rag_knowledge")
            if not pid or not rk:
                continue
            for i, faq in enumerate(_faqs_of(rk)):
                question = _rget(faq, "question", "")
                answer = _rget(faq, "answer", "")
                evidence.append(
                    {
                        "evidence_id": f"POL-{pid}-{i}",
                        "source_type": "policy_faq",
                        "source_id": pid,
                        "product_id": pid,
                        "content": f"Q: {str(question)[:100]} A: {str(answer)[:150]}",
                        "modality": "text",
                        "confidence": 0.9,
                    }
                )
        return RetrievalResult(source_name=self.name, evidence=evidence)
