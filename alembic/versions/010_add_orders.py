"""add orders — 模拟结算订单持久化

Revision ID: 010
Revises: 009
Create Date: 2026-06-08
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("items", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("total_price", sa.Float, default=0.0),
        sa.Column("status", sa.String(32), default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("orders")
