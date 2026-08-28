"""Add source-backed catalog facts for structured retrieval.

Revision ID: 014
Revises: 013
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.create_table(
        "product_facts",
        sa.Column("fact_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("fact_key", sa.String(96), nullable=False),
        sa.Column("value_text", sa.String(512), nullable=False, server_default=""),
        sa.Column("value_number", sa.Float, nullable=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="catalog"),
        sa.Column("source_text", sa.Text, nullable=False, server_default=""),
        sa.Column("source_ref", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extractor", sa.String(32), nullable=False, server_default="rule_v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("product_id", "fact_key", "value_text", "source_text", name="uq_product_facts_source_value"),
    )
    op.create_index("ix_product_facts_product_key", "product_facts", ["product_id", "fact_key"])
    op.create_index("ix_product_facts_key_value", "product_facts", ["fact_key", "value_text"])


def downgrade():
    op.drop_table("product_facts")
