"""add versioned conversation context checkpoints

Revision ID: 015
Revises: 014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.add_column("conversations", sa.Column("context_revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("conversations", sa.Column("active_checkpoint_id", sa.String(64), nullable=True))
    op.create_table(
        "conversation_context_checkpoints",
        sa.Column("checkpoint_id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_through_message_id", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("shopping_state", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("retained_message_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_context_checkpoint_conv_revision", "conversation_context_checkpoints", ["conversation_id", "revision"])


def downgrade():
    op.drop_index("ix_context_checkpoint_conv_revision", table_name="conversation_context_checkpoints")
    op.drop_table("conversation_context_checkpoints")
    op.drop_column("conversations", "active_checkpoint_id")
    op.drop_column("conversations", "context_revision")
