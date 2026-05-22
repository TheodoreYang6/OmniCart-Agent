"""initial — 创建 products / cart_items / user_preferences 表。

Revision ID: 001
Revises: None
Create Date: 2026-05-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("product_id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("brand", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, index=True),
        sa.Column("sub_category", sa.String(64), index=True),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False, index=True),
        sa.Column("image_path", sa.Text, nullable=True),
        sa.Column("skus", postgresql.JSONB, nullable=True),
        sa.Column("rag_knowledge", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "cart_items",
        sa.Column("cart_item_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("sku_id", sa.String(64), nullable=True),
        sa.Column("title", sa.String(256), default=""),
        sa.Column("brand", sa.String(128), default=""),
        sa.Column("price", sa.Numeric(10, 2), default=0.0),
        sa.Column("image_url", sa.Text, default=""),
        sa.Column("quantity", sa.Integer, nullable=False, default=1),
        sa.Column("selected", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("preferences", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", "user_id", name="uq_user_preferences_session_user"),
    )


def downgrade():
    op.drop_table("user_preferences")
    op.drop_table("cart_items")
    op.drop_table("products")
