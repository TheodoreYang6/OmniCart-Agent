"""cart_items 表 — SQLAlchemy ORM 模型。"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Numeric, String, Text,
)

from app.models import Base


class CartItemModel(Base):
    __tablename__ = "cart_items"

    cart_item_id: str = Column(String(64), primary_key=True)
    user_id: str = Column(String(64), nullable=False, index=True)
    product_id: str = Column(String(64), nullable=False)
    sku_id: str | None = Column(String(64), nullable=True)
    sku_label: str = Column(String(256), default="")
    title: str = Column(String(256), default="")
    brand: str = Column(String(128), default="")
    price: float = Column(Numeric(10, 2), default=0.0)
    image_url: str = Column(Text, default="")
    quantity: int = Column(Integer, nullable=False, default=1)
    selected: bool = Column(Boolean, default=True)
    created_at: datetime = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<CartItem {self.cart_item_id} {self.title[:20]}>"
