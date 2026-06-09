"""add user_preference_entries — 独立偏好条目表，替代单行 user_profiles

Revision ID: 006
Revises: 005
Create Date: 2026-06-08

每条偏好是独立行，category 作为检索主键。
用户"我喜欢苹果手机"→ 一条数码电子条目
用户"我是油皮敏感肌"→ 一条美妆个护条目
问"推荐手机"时只匹配数码电子条目，不污染其他品类。
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.create_table(
        "user_preference_entries",
        sa.Column("id", sa.Integer, autoincrement=True),
        sa.Column("entry_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("raw_text", sa.Text, default=""),
        sa.Column("category", sa.String(64), default=""),
        sa.Column("sub_category", sa.String(64), default=""),
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
    op.create_index("idx_upref_user_cat", "user_preference_entries", ["user_id", "category"])
    # entry_id 做唯一索引，防止重复
    op.create_index("idx_upref_entry", "user_preference_entries", ["entry_id"], unique=True)


def downgrade():
    op.drop_table("user_preference_entries")
