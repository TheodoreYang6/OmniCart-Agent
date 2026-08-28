"""Drop unused legacy preference and memory tables.

These tables are not referenced by the runtime ORM, repositories, services, or
API routes. Their replacements are ``user_preference_entries`` and the
conversation context snapshot. The migration was prepared after verifying that
all four tables are empty in the active database.

Revision ID: 012
Revises: 011
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.drop_table("memory_usage_traces")
    op.drop_table("memory_audit_logs")
    op.drop_table("user_memories")
    op.drop_table("user_preferences")


def downgrade():
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("preferences", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", "user_id", name="uq_user_preferences_session_user"),
    )
    op.create_index("ix_user_preferences_session_id", "user_preferences", ["session_id"])

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
