"""add_memory_system_tables — conversations / messages / behavior_events / user_memories / audit / traces

Revision ID: 002
Revises: 001
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    # ---- conversations ----
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), nullable=False, index=True),
        sa.Column("title", sa.String(256), default=""),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ---- conversation_messages ----
    op.create_table(
        "conversation_messages",
        sa.Column("message_id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64),
                  sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, default=""),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("product_refs", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("evidence_refs", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("memory_refs", postgresql.JSONB, default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("extra_data", postgresql.JSONB, default=sa.text("'{}'")),
    )
    op.create_index("ix_cmessages_conv_id_created", "conversation_messages",
                    ["conversation_id", "created_at"])

    # ---- behavior_events ----
    op.create_table(
        "behavior_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), nullable=False, index=True),
        sa.Column("conversation_id", sa.String(64), nullable=False, index=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=True),
        sa.Column("query", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("extra_data", postgresql.JSONB, default=sa.text("'{}'")),
    )
    op.create_index("ix_bevents_user_created", "behavior_events", ["user_id", "created_at"])
    op.create_index("ix_bevents_session_created", "behavior_events", ["session_id", "created_at"])

    # ---- user_memories ----
    op.create_table(
        "user_memories",
        sa.Column("memory_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), default=""),
        sa.Column("conversation_id", sa.String(64), default=""),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, default=""),
        sa.Column("structured_value", postgresql.JSONB, default=sa.text("'{}'")),
        sa.Column("source", sa.String(32), nullable=False, default="explicit_user"),
        sa.Column("confidence", sa.Float, default=1.0),
        sa.Column("status", sa.String(32), nullable=False, default="active", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decay_weight", sa.Float, default=1.0),
        sa.Column("evidence_refs", postgresql.JSONB, default=sa.text("'[]'")),
    )
    op.create_index("ix_umemories_user_status", "user_memories", ["user_id", "status"])
    op.create_index("ix_umemories_user_type", "user_memories", ["user_id", "memory_type"])

    # ---- memory_audit_logs ----
    op.create_table(
        "memory_audit_logs",
        sa.Column("audit_id", sa.String(64), primary_key=True),
        sa.Column("memory_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("old_value", postgresql.JSONB, nullable=True),
        sa.Column("new_value", postgresql.JSONB, nullable=True),
        sa.Column("actor", sa.String(64), default="system"),
        sa.Column("reason", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_maudit_memory_created", "memory_audit_logs", ["memory_id", "created_at"])
    op.create_index("ix_maudit_user_created", "memory_audit_logs", ["user_id", "created_at"])

    # ---- memory_usage_traces ----
    op.create_table(
        "memory_usage_traces",
        sa.Column("trace_id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), default="", index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), default="", index=True),
        sa.Column("conversation_id", sa.String(64), default="", index=True),
        sa.Column("memory_id", sa.String(64), nullable=False, index=True),
        sa.Column("usage_type", sa.String(32), default="used"),
        sa.Column("reason", sa.String(256), default=""),
        sa.Column("score", sa.Float, default=0.0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_mtrace_request", "memory_usage_traces", ["request_id", "created_at"])
    op.create_index("ix_mtrace_user_memory", "memory_usage_traces", ["user_id", "memory_id"])


def downgrade():
    op.drop_table("memory_usage_traces")
    op.drop_table("memory_audit_logs")
    op.drop_table("user_memories")
    op.drop_table("behavior_events")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
