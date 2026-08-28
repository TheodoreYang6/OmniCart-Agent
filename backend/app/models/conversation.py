"""Conversation & ConversationMessage SQLAlchemy ORM models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ConversationModel(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id("CONV"))
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active / archived
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_snapshot: Mapped[dict] = mapped_column("context_snapshot", JSONB, default=dict)
    last_message: Mapped[str] = mapped_column(Text, default="")
    # 会话投影的乐观并发版本与当前有效检查点。原 context_snapshot 保留作兼容读。
    context_revision: Mapped[int] = mapped_column(default=0)
    active_checkpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ConversationMessageModel(Base):
    __tablename__ = "conversation_messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id("MSG"))
    conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_refs: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)
    memory_refs: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    extra_data: Mapped[dict] = mapped_column("extra_data", JSONB, default=dict)

    __table_args__ = (
        Index("ix_cmessages_conv_id_created", "conversation_id", "created_at"),
    )


class ConversationContextCheckpointModel(Base):
    """可重建的会话上下文检查点；历史消息仍是唯一事实源。"""

    __tablename__ = "conversation_context_checkpoints"

    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id("CKP"))
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False, default=0)
    source_through_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    shopping_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    retained_message_ids: Mapped[list] = mapped_column(JSONB, default=list)
    token_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(24), default="active")  # active / superseded / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_context_checkpoint_conv_revision", "conversation_id", "revision"),
    )
