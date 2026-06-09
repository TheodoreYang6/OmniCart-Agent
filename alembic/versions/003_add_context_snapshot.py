"""add_context_snapshot_and_last_message_to_conversations

Revision ID: 003
Revises: 002
Create Date: 2026-05-27

为 Memory Lite P0 增加:
- context_snapshot (JSONB) — 购物任务上下文快照
- last_message (TEXT) — 最后一条消息预览
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.add_column("conversations",
        sa.Column("context_snapshot", postgresql.JSONB, server_default=sa.text("'{}'"), nullable=False))
    op.add_column("conversations",
        sa.Column("last_message", sa.Text, server_default=sa.text("''"), nullable=False))


def downgrade():
    op.drop_column("conversations", "last_message")
    op.drop_column("conversations", "context_snapshot")
