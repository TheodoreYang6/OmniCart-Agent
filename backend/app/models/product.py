"""products 表 — SQLAlchemy ORM 模型。"""

import json
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Numeric, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base


class ProductModel(Base):
    __tablename__ = "products"

    product_id: str = Column(String(64), primary_key=True)
    title: str = Column(Text, nullable=False)
    brand: str = Column(String(128), nullable=False)
    category: str = Column(String(64), nullable=False, index=True)
    sub_category: str = Column(String(64), index=True)
    base_price: float = Column(Numeric(10, 2), nullable=False, index=True)
    image_path: str | None = Column(Text, nullable=True)
    skus: list | None = Column(JSONB, nullable=True)
    rag_knowledge: dict | None = Column(JSONB, nullable=True)
    # V5 派生聚合列（从 rag_knowledge 回填，供排序/过滤/展示，避免每次解析 JSONB）
    avg_rating = Column(Numeric(3, 2), default=0, index=True)
    review_count = Column(Integer, default=0)
    positive_count = Column(Integer, default=0)
    negative_count = Column(Integer, default=0)
    risk_tags = Column(JSONB, nullable=True)
    # V5 关键词检索文本（标题+品牌+品类+营销拼接），pg_trgm GIN 索引在迁移中创建
    # 中文不适合 PG 默认全文分词，改用 trigram 做子串/模糊匹配
    search_text = Column(Text, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<Product {self.product_id} {self.title[:30]}>"
