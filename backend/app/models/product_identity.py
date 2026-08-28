"""Catalog identity tables used by the precise product resolver."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ProductIdentityModel(Base):
    __tablename__ = "product_identities"

    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True
    )
    brand_key: Mapped[str] = mapped_column(String(128), default="")
    product_line_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    family_key: Mapped[str] = mapped_column(String(256), default="", index=True)
    model_key: Mapped[str] = mapped_column(String(256), default="")
    variant_key: Mapped[str] = mapped_column(String(256), default="")
    identity_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="generated")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ProductAliasModel(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (UniqueConstraint("product_id", "alias_normalized", name="uq_product_aliases_product_alias"),)

    alias_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False
    )
    alias_normalized: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    alias_display: Mapped[str] = mapped_column(String(512), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), default="generated")
    source: Mapped[str] = mapped_column(String(32), default="generated")
