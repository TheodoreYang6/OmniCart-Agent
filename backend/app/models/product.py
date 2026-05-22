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
