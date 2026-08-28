"""Add catalog identity and alias tables for precise product resolution.

Revision ID: 013
Revises: 012
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.create_table(
        "product_identities",
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("brand_key", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_line_key", sa.String(128), nullable=False, server_default=""),
        sa.Column("family_key", sa.String(256), nullable=False, server_default=""),
        sa.Column("model_key", sa.String(256), nullable=False, server_default=""),
        sa.Column("variant_key", sa.String(256), nullable=False, server_default=""),
        sa.Column("identity_text", sa.Text, nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="generated"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_product_identities_line", "product_identities", ["product_line_key"])
    op.create_index("ix_product_identities_family", "product_identities", ["family_key"])
    op.create_index("ix_product_identities_brand_line", "product_identities", ["brand_key", "product_line_key"])

    op.create_table(
        "product_aliases",
        sa.Column("alias_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias_normalized", sa.String(512), nullable=False),
        sa.Column("alias_display", sa.String(512), nullable=False),
        sa.Column("alias_type", sa.String(32), nullable=False, server_default="generated"),
        sa.Column("source", sa.String(32), nullable=False, server_default="generated"),
        sa.UniqueConstraint("product_id", "alias_normalized", name="uq_product_aliases_product_alias"),
    )
    op.create_index("ix_product_aliases_normalized", "product_aliases", ["alias_normalized"])
    op.execute(
        "CREATE INDEX ix_product_aliases_normalized_trgm "
        "ON product_aliases USING gin (alias_normalized gin_trgm_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_product_aliases_normalized_trgm")
    op.drop_table("product_aliases")
    op.drop_table("product_identities")
