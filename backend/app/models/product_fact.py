"""Source-backed, queryable product facts.

Facts are deliberately kept separate from ``rag_knowledge``.  The latter is
useful evidence for a human/LLM, but it is not a safe structure on which to
apply hard retrieval constraints.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ProductFactModel(Base):
    __tablename__ = "product_facts"
    __table_args__ = (
        UniqueConstraint("product_id", "fact_key", "value_text", "source_text",
                         name="uq_product_facts_source_value"),
    )

    fact_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.product_id", ondelete="CASCADE"), index=True
    )
    fact_key: Mapped[str] = mapped_column(String(96), index=True)
    value_text: Mapped[str] = mapped_column(String(512), default="")
    value_number: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="catalog")
    source_text: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[dict] = mapped_column(JSONB, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    extractor: Mapped[str] = mapped_column(String(32), default="rule_v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
