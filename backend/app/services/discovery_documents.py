"""Build index documents from catalog models and source-backed product facts.

Construction belongs to the service layer because it coordinates schema
contracts with fact-extraction behavior. Keeping it here preserves the rule
that ``app.schemas`` contains data contracts only.
"""

from __future__ import annotations

from app.schemas.discovery_document import DiscoveryDocument, EvidenceDocument
from app.services.product_facts import build_discovery_text, extract_product_facts


def build_discovery_document(product) -> DiscoveryDocument:
    facts = extract_product_facts(product)
    payload = {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": float(product.base_price),
        "fact_keys": sorted({fact.fact_key for fact in facts}),
        "facts": [fact.model_payload() for fact in facts],
    }
    return DiscoveryDocument(product.product_id, build_discovery_text(product, facts), payload)


def build_evidence_documents(product) -> list[EvidenceDocument]:
    docs: list[EvidenceDocument] = []
    knowledge = product.rag_knowledge
    if not knowledge:
        return docs

    base = {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
    }
    if knowledge.marketing_description:
        text = knowledge.marketing_description
        docs.append(
            EvidenceDocument(
                f"{product.product_id}|marketing|0",
                product.product_id,
                "marketing",
                text,
                dict(base, source_type="marketing", content=text),
            )
        )
    for index, faq in enumerate(knowledge.official_faq or []):
        text = f"Q: {faq.question} A: {faq.answer}"
        docs.append(
            EvidenceDocument(
                f"{product.product_id}|faq|{index}",
                product.product_id,
                "faq",
                text,
                dict(base, source_type="faq", source_index=index, content=text),
            )
        )
    for index, review in enumerate(knowledge.user_reviews or []):
        text = f"评分{review.rating}/5: {review.content}"
        docs.append(
            EvidenceDocument(
                f"{product.product_id}|review|{index}",
                product.product_id,
                "review",
                text,
                dict(
                    base,
                    source_type="review",
                    source_index=index,
                    review_rating=review.rating,
                    content=text,
                ),
            )
        )
    return docs
