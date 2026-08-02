"""统一商品分块 Schema (V5) — 借鉴 amap-ai-agent ha3/schema.py 的 LongTermFactRow 模式。

集中管理「商品 → 向量块」的字段映射与序列化，schema 变更只改一处：
- ChunkType         块类型枚举 (summary / mkt / faq / rev)
- ProductChunk      单个块的领域模型 + Qdrant payload 双向映射
- build_chunks()    商品 → 多块拆分（summary 1 + mkt 1 + faq N + rev N）
- compute_review_aggregates()  商品 → 评价派生聚合（供 PG 派生列 + 展示复用）
- chunk_point_id()  chunk_id → 稳定 uuid5 点 ID

索引脚本 (scripts/index_product_chunks.py) 与检索器 (HybridRetriever) 均从此模块取用，
避免各自维护一套字段映射。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.schemas.product import Product

_NAMESPACE = uuid.NAMESPACE_DNS


class ChunkType(str, Enum):
    """块类型。summary 块可作为产品级视图（筛 chunk_type='summary'）。"""

    SUMMARY = "summary"
    MKT = "mkt"
    FAQ = "faq"
    REV = "rev"


@dataclass
class ProductChunk:
    """单个商品块 — 领域模型 + Qdrant payload 映射。"""

    chunk_id: str
    product_id: str
    chunk_type: str
    chunk_index: int
    title: str
    brand: str
    category: str
    sub_category: str
    price: float
    text: str
    # 口碑聚合（V6：挂每块 payload，支持服务端“高分/口碑好”过滤与展示层免回读 PG）
    avg_rating: float = 0.0
    review_count: int = 0
    negative_count: int = 0
    # 类型专属可选字段
    faq_question: str = ""
    review_rating: int = 0
    review_nickname: str = ""

    def to_qdrant_payload(self) -> dict[str, Any]:
        """序列化为 Qdrant payload（含用于过滤的索引字段 + 用于展示的正文）。"""
        payload: dict[str, Any] = {
            "product_id": self.product_id,
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "chunk_index": self.chunk_index,
            "title": self.title,
            "brand": self.brand,
            "category": self.category,
            "sub_category": self.sub_category,
            "price": self.price,
            "text": self.text,
            "avg_rating": self.avg_rating,
            "review_count": self.review_count,
            "negative_count": self.negative_count,
        }
        if self.faq_question:
            payload["faq_question"] = self.faq_question
        if self.review_rating:
            payload["review_rating"] = self.review_rating
        if self.review_nickname:
            payload["review_nickname"] = self.review_nickname
        return payload

    @classmethod
    def from_qdrant_payload(cls, payload: dict[str, Any]) -> "ProductChunk":
        return cls(
            chunk_id=str(payload.get("chunk_id", "")),
            product_id=str(payload.get("product_id", "")),
            chunk_type=str(payload.get("chunk_type", "")),
            chunk_index=int(payload.get("chunk_index", 0) or 0),
            title=str(payload.get("title", "")),
            brand=str(payload.get("brand", "")),
            category=str(payload.get("category", "")),
            sub_category=str(payload.get("sub_category", "")),
            price=float(payload.get("price", 0) or 0),
            text=str(payload.get("text", "")),
            avg_rating=float(payload.get("avg_rating", 0) or 0),
            review_count=int(payload.get("review_count", 0) or 0),
            negative_count=int(payload.get("negative_count", 0) or 0),
            faq_question=str(payload.get("faq_question", "")),
            review_rating=int(payload.get("review_rating", 0) or 0),
            review_nickname=str(payload.get("review_nickname", "")),
        )

    def point_id(self) -> str:
        return chunk_point_id(self.chunk_id)


def chunk_point_id(chunk_id: str) -> str:
    """chunk_id → 稳定 uuid5 点 ID（幂等 upsert）。"""
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


def _base_fields(product: Product, chunk_type: str, chunk_index: int) -> dict[str, Any]:
    return {
        "product_id": product.product_id,
        "chunk_type": chunk_type,
        "chunk_index": chunk_index,
        "chunk_id": f"{product.product_id}|{chunk_type}|{chunk_index}",
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": product.base_price,
    }


def _sku_spec_text(product: Product, max_len: int = 80) -> str:
    """SKU 规格按维度聚合去重（V6：规格语义入向量，支持“大容量/高承重/XL码”类查询）。"""
    dims: dict[str, list[str]] = {}
    for sku in product.skus or []:
        for k, v in (sku.properties or {}).items():
            vals = dims.setdefault(str(k), [])
            if str(v) not in vals:
                vals.append(str(v))
    if not dims:
        return ""
    text = " ".join(f"{k}:{'/'.join(vs[:4])}" for k, vs in dims.items())
    return text[:max_len]


def build_chunks(product: Product) -> list[ProductChunk]:
    """将单件商品拆分为多个块：summary(1) + mkt(1) + faq(N) + rev(N)。

    V6 要点：
    - Contextual Prefix（Anthropic Contextual Retrieval）：mkt/rev 块前缀
      「[品牌 子品类]」商品上下文，消除跨商品同质内容的混淆命中；
      faq 块不加前缀（消融实验：FAQ 问句自带商品指向，加前缀反稀释问句语义——
      无前缀 hit@1 0.969 vs 短前缀 0.891 vs v4 基线 0.938）；
    - summary 块并入 SKU 规格维度；
    - FAQ 答案截断 400（新数据 15% 超 200 字，尾部是参数与操作建议）；
    - rev 块去昵称（噪音退出 embedding 文本，保留在 payload）；
    - 每块携带口碑聚合 payload。
    """
    chunks: list[ProductChunk] = []
    rk = product.rag_knowledge
    agg = compute_review_aggregates(product)
    rating_fields = {
        "avg_rating": agg["avg_rating"],
        "review_count": agg["review_count"],
        "negative_count": agg["negative_count"],
    }
    # 上下文前缀：品牌 + 子品类（消混淆的最小充分字段，避免长标题淹没块主体语义）
    ctx_prefix = f"[{product.brand} {product.sub_category}] "

    # summary — 产品基本标识 + 规格维度
    summary_text = (
        f"[产品] {product.title} | [品牌] {product.brand} | "
        f"[品类] {product.category} > {product.sub_category} | [价格] ¥{product.base_price:.0f}"
    )
    spec = _sku_spec_text(product)
    if spec:
        summary_text += f" | [规格] {spec}"
    chunks.append(ProductChunk(text=summary_text, **rating_fields,
                               **_base_fields(product, "summary", 0)))

    if not rk:
        return chunks

    # mkt — 营销描述
    if rk.marketing_description:
        chunks.append(
            ProductChunk(text=ctx_prefix + rk.marketing_description.strip(),
                         **rating_fields, **_base_fields(product, "mkt", 0))
        )

    # faq — 每条独立（答案截 400；不加前缀，问句自带商品指向，前缀反而稀释语义）
    for i, faq in enumerate(rk.official_faq or []):
        text = f"Q: {faq.question.strip()} A: {faq.answer.strip()[:400]}"
        chunks.append(
            ProductChunk(
                text=text, faq_question=faq.question.strip(), **rating_fields,
                **_base_fields(product, "faq", i)
            )
        )

    # rev — 每条独立（昵称退出 embedding 文本，仅留 payload）
    for i, rev in enumerate(rk.user_reviews or []):
        text = f"{ctx_prefix}评分{rev.rating}/5: {rev.content.strip()[:200]}"
        chunks.append(
            ProductChunk(
                text=text,
                review_rating=rev.rating,
                review_nickname=rev.nickname,
                **rating_fields,
                **_base_fields(product, "rev", i),
            )
        )

    return chunks


def compute_review_aggregates(product: Product) -> dict[str, Any]:
    """从评价计算派生聚合（供 PG 派生列回填 + 展示层复用，口径与 products API 一致）。"""
    reviews = product.rag_knowledge.user_reviews if product.rag_knowledge else []
    if not reviews:
        return {
            "avg_rating": 0.0,
            "review_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "risk_tags": [],
        }
    ratings = [r.rating for r in reviews]
    avg = sum(ratings) / len(ratings)
    positive = sum(1 for r in ratings if r >= 4)
    negative = sum(1 for r in ratings if r <= 2)
    risk_tags: list[str] = []
    if negative >= 2:
        risk_tags.append("多差评风险")
    elif negative == 1:
        risk_tags.append("个别差评")
    if len(ratings) >= 3 and avg < 3.5:
        risk_tags.append("综合评分偏低")
    return {
        "avg_rating": round(avg, 2),
        "review_count": len(ratings),
        "positive_count": positive,
        "negative_count": negative,
        "risk_tags": risk_tags,
    }
