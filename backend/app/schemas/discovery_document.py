"""Documents for the v8 split discovery/evidence indexes."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.product_facts import build_discovery_text, extract_product_facts


@dataclass(frozen=True)
class DiscoveryDocument:
    product_id: str
    text: str
    payload: dict


@dataclass(frozen=True)
class EvidenceDocument:
    evidence_id: str
    product_id: str
    source_type: str
    text: str
    payload: dict


def build_discovery_document(product) -> DiscoveryDocument:
    facts = extract_product_facts(product)
    payload = {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": float(product.base_price),
        "fact_keys": sorted({f.fact_key for f in facts}),
        "facts": [f.model_payload() for f in facts],
    }
    return DiscoveryDocument(product.product_id, build_discovery_text(product, facts), payload)


def build_evidence_documents(product) -> list[EvidenceDocument]:
    docs: list[EvidenceDocument] = []
    knowledge = product.rag_knowledge
    if not knowledge:
        return docs
    base = {"product_id": product.product_id, "title": product.title, "brand": product.brand,
            "category": product.category, "sub_category": product.sub_category}
    if knowledge.marketing_description:
        text = knowledge.marketing_description
        docs.append(EvidenceDocument(f"{product.product_id}|marketing|0", product.product_id, "marketing",
                                     text, dict(base, source_type="marketing", content=text)))
    for i, faq in enumerate(knowledge.official_faq or []):
        text = f"Q: {faq.question} A: {faq.answer}"
        docs.append(EvidenceDocument(f"{product.product_id}|faq|{i}", product.product_id, "faq", text,
                                     dict(base, source_type="faq", source_index=i, content=text)))
    for i, review in enumerate(knowledge.user_reviews or []):
        text = f"评分{review.rating}/5: {review.content}"
        docs.append(EvidenceDocument(f"{product.product_id}|review|{i}", product.product_id, "review", text,
                                     dict(base, source_type="review", source_index=i,
                                          review_rating=review.rating, content=text)))
    return docs
