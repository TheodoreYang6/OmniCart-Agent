"""add user_profiles — 长期偏好画像表

Revision ID: 004
Revises: 003
Create Date: 2026-06-07

一人一行，JSONB 存 categories/brands/devices/scenarios/budget/avoid_tags/must_tags。
解析后的结构化偏好，供推荐链路 query enhancement 和 context 引用。
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("raw_text", sa.Text, default=""),
        sa.Column("categories", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("sub_categories", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("brands", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("devices", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("scenarios", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("budget_min", sa.Float, nullable=True),
        sa.Column("budget_max", sa.Float, nullable=True),
        sa.Column("avoid_tags", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("must_tags", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("user_profiles")
