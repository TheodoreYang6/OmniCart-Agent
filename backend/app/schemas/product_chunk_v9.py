"""V9 商品多视角 Chunk。

V9 不再把一整段营销文案或单条评论当成商品的全部语义。每一块都带有商品
身份上下文，并保留来源定位；召回后按 ``product_id`` 聚合，评论只能提供支持
证据，不能单独决定一个商品进入结果。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.schemas.product import Product
from app.schemas.product_chunk import compute_review_aggregates

_NAMESPACE = uuid.NAMESPACE_URL
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


@dataclass
class ProductChunkV9:
    chunk_id: str
    product_id: str
    chunk_type: str
    chunk_index: int
    text: str
    title: str
    brand: str
    category: str
    sub_category: str
    price: float
    source_type: str = ""
    source_ref: str = ""
    source_refs: list[str] = field(default_factory=list)
    paragraph_no: int = 0
    review_rating: int = 0
    avg_rating: float = 0.0
    review_count: int = 0
    negative_count: int = 0

    def point_id(self) -> str:
        return str(uuid.uuid5(_NAMESPACE, self.chunk_id))

    def to_qdrant_payload(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "title": self.title,
            "brand": self.brand,
            "category": self.category,
            "sub_category": self.sub_category,
            "price": self.price,
            "source_type": self.source_type or self.chunk_type,
            "source_ref": self.source_ref,
            "source_refs": self.source_refs,
            "paragraph_no": self.paragraph_no,
            "review_rating": self.review_rating,
            "avg_rating": self.avg_rating,
            "review_count": self.review_count,
            "negative_count": self.negative_count,
        }


def _prefix(product: Product) -> str:
    """所有块注入最小、稳定的身份锚点，防止“好用/续航/保湿”等泛词串商品。"""
    return f"[商品] {product.title} | [品牌] {product.brand} | [品类] {product.category}/{product.sub_category} | "


def _sku_text(product: Product) -> str:
    dimensions: dict[str, list[str]] = {}
    for sku in product.skus or []:
        for key, value in (sku.properties or {}).items():
            values = dimensions.setdefault(str(key), [])
            if str(value) not in values:
                values.append(str(value))
    return "；".join(f"{key}:{'/'.join(values[:6])}" for key, values in dimensions.items())


def split_semantic_text(text: str, *, min_chars: int = 180, max_chars: int = 320,
                        overlap: int = 40) -> list[str]:
    """按段落/列表/句末切片，长文本控制在 180--320 中文字符附近。

    短段不硬拼无关段落；超长单句采用字符兜底。后一块带前块末尾 40 字，保证
    规格与转折语义不会被边界截断。
    """
    text = re.sub(r"\r\n?", "\n", (text or "")).strip()
    if not text:
        return []
    paragraphs = [p.strip(" -•\t") for p in re.split(r"\n\s*\n|\n(?=[-•\d])", text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs or [text]:
        units.extend(piece.strip() for piece in _SENTENCE_BOUNDARY.split(paragraph) if piece.strip())
    chunks: list[str] = []
    current = ""
    for unit in units:
        # 超长句先切，避免一个块无限长。
        pieces = [unit[i:i + max_chars] for i in range(0, len(unit), max_chars)] or [unit]
        for piece in pieces:
            joiner = "" if not current else " "
            if current and len(current) + len(joiner) + len(piece) > max_chars:
                chunks.append(current)
                tail = current[-overlap:] if len(current) > overlap else current
                current = (tail + " " + piece).strip()
            else:
                current = (current + joiner + piece).strip()
            if len(current) >= max_chars:
                chunks.append(current[:max_chars])
                current = current[max(0, max_chars - overlap):].strip()
    if current:
        chunks.append(current)
    # 单位文本很短时可小于 min_chars；宁可短而来源清晰，也不把不同事实硬连起来。
    return [chunk for chunk in chunks if chunk]


def _make(product: Product, chunk_type: str, index: int, text: str, **extra: Any) -> ProductChunkV9:
    agg = compute_review_aggregates(product)
    return ProductChunkV9(
        chunk_id=f"{product.product_id}|v9|{chunk_type}|{index}",
        product_id=product.product_id,
        chunk_type=chunk_type,
        chunk_index=index,
        text=text,
        title=product.title,
        brand=product.brand,
        category=product.category,
        sub_category=product.sub_category,
        price=float(product.base_price or 0),
        avg_rating=float(agg["avg_rating"]),
        review_count=int(agg["review_count"]),
        negative_count=int(agg["negative_count"]),
        **extra,
    )


def _review_aspects(product: Product) -> Iterable[tuple[str, list[str]]]:
    """来源可追溯的评论双层表达：正向与注意点各保留若干原评，不臆造主题。"""
    reviews = product.rag_knowledge.user_reviews if product.rag_knowledge else []
    positive = [(i, r) for i, r in enumerate(reviews) if r.rating >= 4 and r.content.strip()]
    caution = [(i, r) for i, r in enumerate(reviews) if r.rating <= 3 and r.content.strip()]
    for label, values in (("好评体验", positive), ("使用注意", caution)):
        if not values:
            continue
        selected = values[:3]
        refs = [f"review:{i}" for i, _ in selected]
        snippets = "；".join(f"{r.rating}/5 {r.content.strip()[:100]}" for _, r in selected)
        yield f"[{label}] {snippets}", refs


def build_chunks_v9(product: Product, facts: list[dict[str, Any]] | None = None) -> list[ProductChunkV9]:
    """构建 identity/facts/marketing/FAQ/review/review_aspect 六类 Chunk。"""
    chunks: list[ProductChunkV9] = []
    prefix = _prefix(product)
    identity = f"{prefix}[价格] ¥{product.base_price:g}"
    if specs := _sku_text(product):
        identity += f" | [规格] {specs}"
    chunks.append(_make(product, "identity", 0, identity, source_type="product"))

    fact_lines: list[str] = []
    for fact in facts or []:
        field_name = str(fact.get("field_name") or fact.get("fact_key") or fact.get("key") or "")
        value = str(fact.get("value") or fact.get("value_text") or fact.get("normalized_value") or "")
        source = str(fact.get("source_text") or fact.get("evidence") or "")
        if field_name and value:
            fact_lines.append(f"{field_name}:{value}" + (f"（依据：{source[:100]}）" if source else ""))
    if fact_lines:
        for idx, part in enumerate(split_semantic_text("；".join(fact_lines))):
            chunks.append(_make(product, "facts", idx, prefix + "[已验证属性] " + part,
                                source_type="facts", source_ref=f"facts:{idx}"))

    rag = product.rag_knowledge
    if not rag:
        return chunks
    for idx, part in enumerate(split_semantic_text(rag.marketing_description or "")):
        chunks.append(_make(product, "marketing", idx, prefix + "[商品说明] " + part,
                            source_type="marketing", source_ref=f"marketing:{idx}", paragraph_no=idx))
    faq_idx = 0
    for source_index, faq in enumerate(rag.official_faq or []):
        question = (faq.question or "").strip()
        answer_parts = split_semantic_text((faq.answer or "").strip()) or [""]
        for answer_index, answer in enumerate(answer_parts):
            text = prefix + f"[官方问答] 问：{question} 答：{answer}"
            chunks.append(_make(product, "faq", faq_idx, text, source_type="faq",
                                source_ref=f"faq:{source_index}:{answer_index}"))
            faq_idx += 1
    review_idx = 0
    for source_index, review in enumerate(rag.user_reviews or []):
        for part_index, part in enumerate(split_semantic_text((review.content or "").strip()) or [""]):
            if not part:
                continue
            chunks.append(_make(product, "review", review_idx,
                                prefix + f"[用户评价 {review.rating}/5] {part}", source_type="review",
                                source_ref=f"review:{source_index}:{part_index}", review_rating=review.rating))
            review_idx += 1
    aspect_idx = 0
    for text, refs in _review_aspects(product):
        chunks.append(_make(product, "review_aspect", aspect_idx, prefix + text,
                            source_type="review_aspect", source_ref=refs[0], source_refs=refs))
        aspect_idx += 1
    return chunks
