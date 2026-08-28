"""Conversation Repository — PG async + sync wrapper.

Conversation CRUD + message append/list. PG is authoritative; no memory fallback
because messages are facts that must survive restarts.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_sync, run_async
from app.models.conversation import (
    ConversationModel, ConversationMessageModel, ConversationContextCheckpointModel,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _utcnow():
    return datetime.now(timezone.utc)


class ConversationRepository:
    """Async-first conversation repository with sync bridge."""

    # ---- helpers ----

    @staticmethod
    async def _aget_session() -> AsyncSession:
        factory = get_session_sync()
        if factory is None:
            raise RuntimeError("PostgreSQL is not configured")
        async with factory() as session:
            yield session

    # ---- Conversation CRUD ----

    async def acreate(self, user_id: str, session_id: str, title: str = "") -> ConversationModel:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            conv = ConversationModel(
                conversation_id=_new_id("CONV"),
                user_id=user_id,
                session_id=session_id,
                title=title or f"Chat {_utcnow().strftime('%m-%d %H:%M')}",
                status="active",
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            return conv
        finally:
            await gen.aclose()

    async def aget(self, conversation_id: str) -> Optional[ConversationModel]:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            )
            return result.scalar_one_or_none()
        finally:
            await gen.aclose()

    async def alist_by_user(self, user_id: str, limit: int = 20) -> list[ConversationModel]:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(ConversationModel)
                .where(ConversationModel.user_id == user_id)
                .order_by(desc(ConversationModel.updated_at))
                .limit(limit)
            )
            return list(result.scalars().all())
        finally:
            await gen.aclose()

    async def aget_latest_by_session(self, user_id: str, session_id: str) -> Optional[ConversationModel]:
        """按 session_id 取最近活跃会话（P0-1 会话连续性：不回传 cid 的客户端同 session 复用）。"""
        if not session_id:
            return None
        gen = self._aget_session()
        session = await anext(gen)
        try:
            stmt = select(ConversationModel).where(ConversationModel.session_id == session_id)
            if user_id:
                stmt = stmt.where(ConversationModel.user_id == user_id)
            stmt = stmt.order_by(desc(ConversationModel.updated_at)).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await gen.aclose()

    async def aupdate(self, conversation_id: str, **kwargs) -> Optional[ConversationModel]:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if not conv:
                return None
            for k, v in kwargs.items():
                if hasattr(conv, k) and v is not None:
                    setattr(conv, k, v)
            conv.updated_at = _utcnow()
            await session.commit()
            await session.refresh(conv)
            return conv
        finally:
            await gen.aclose()

    # ---- Message CRUD ----

    async def aappend_message(self, conversation_id: str, user_id: str, session_id: str,
                              role: str, content: str, image_url: str | None = None,
                              product_refs: list | None = None, evidence_refs: list | None = None,
                              memory_refs: list | None = None, metadata: dict | None = None) -> ConversationMessageModel:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            msg = ConversationMessageModel(
                message_id=_new_id("MSG"),
                conversation_id=conversation_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                image_url=image_url,
                product_refs=product_refs or [],
                evidence_refs=evidence_refs or [],
                memory_refs=memory_refs or [],
                created_at=_utcnow(),
                extra_data=metadata or {},
            )
            session.add(msg)
            # touch conversation updated_at
            conv_result = await session.execute(
                select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv:
                conv.updated_at = _utcnow()
            await session.commit()
            await session.refresh(msg)
            return msg
        finally:
            await gen.aclose()

    async def alist_messages(self, conversation_id: str, limit: int = 50) -> list[ConversationMessageModel]:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            # 调用者将 limit 用作“最近 N 条”的上下文窗口。原先按时间正序直接
            # limit，会在长会话中永远返回最早的消息，使追问和记忆逐渐失真。
            # 先倒序截取最新窗口，再恢复成自然对话顺序交给上层。
            result = await session.execute(
                select(ConversationMessageModel)
                .where(ConversationMessageModel.conversation_id == conversation_id)
                .order_by(desc(ConversationMessageModel.created_at))
                .limit(limit)
            )
            return list(reversed(list(result.scalars().all())))
        finally:
            await gen.aclose()

    async def aget_active_checkpoint(self, conversation_id: str) -> Optional[ConversationContextCheckpointModel]:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(ConversationContextCheckpointModel)
                .where(
                    ConversationContextCheckpointModel.conversation_id == conversation_id,
                    ConversationContextCheckpointModel.status == "active",
                )
                .order_by(desc(ConversationContextCheckpointModel.revision))
                .limit(1)
            )
            return result.scalar_one_or_none()
        finally:
            await gen.aclose()

    async def acommit_checkpoint(
        self, conversation_id: str, *, expected_revision: int, summary: str,
        shopping_state: dict, source_through_message_id: str | None,
        retained_message_ids: list[str], token_count: int,
    ) -> Optional[ConversationContextCheckpointModel]:
        """原子提交检查点；revision 不一致说明已有更新，调用方应重新投影。"""
        gen = self._aget_session()
        session = await anext(gen)
        try:
            conv_result = await session.execute(
                select(ConversationModel).where(ConversationModel.conversation_id == conversation_id).with_for_update()
            )
            conv = conv_result.scalar_one_or_none()
            if not conv or int(conv.context_revision or 0) != int(expected_revision):
                await session.rollback()
                return None
            await session.execute(
                update(ConversationContextCheckpointModel)
                .where(
                    ConversationContextCheckpointModel.conversation_id == conversation_id,
                    ConversationContextCheckpointModel.status == "active",
                )
                .values(status="superseded")
            )
            checkpoint = ConversationContextCheckpointModel(
                checkpoint_id=_new_id("CKP"), conversation_id=conversation_id,
                revision=expected_revision + 1, summary=summary[:1600],
                shopping_state=shopping_state or {}, source_through_message_id=source_through_message_id,
                retained_message_ids=retained_message_ids or [], token_count=int(token_count or 0), status="active",
            )
            session.add(checkpoint)
            conv.context_revision = expected_revision + 1
            conv.active_checkpoint_id = checkpoint.checkpoint_id
            conv.updated_at = _utcnow()
            await session.commit()
            await session.refresh(checkpoint)
            return checkpoint
        except Exception:
            await session.rollback()
            raise
        finally:
            await gen.aclose()

    # ---- Sync wrappers ----

    def create(self, user_id: str, session_id: str, title: str = "") -> ConversationModel:
        return run_async(self.acreate(user_id, session_id, title))

    def get(self, conversation_id: str) -> Optional[ConversationModel]:
        return run_async(self.aget(conversation_id))

    def list_by_user(self, user_id: str, limit: int = 20) -> list[ConversationModel]:
        return run_async(self.alist_by_user(user_id, limit))

    def get_latest_by_session(self, user_id: str, session_id: str) -> Optional[ConversationModel]:
        return run_async(self.aget_latest_by_session(user_id, session_id))

    def append_message(self, conversation_id: str, user_id: str, session_id: str,
                       role: str, content: str, **kwargs) -> ConversationMessageModel:
        return run_async(self.aappend_message(conversation_id, user_id, session_id, role, content, **kwargs))

    def list_messages(self, conversation_id: str, limit: int = 50) -> list[ConversationMessageModel]:
        return run_async(self.alist_messages(conversation_id, limit))


    async def adelete(self, conversation_id: str) -> bool:
        """硬删除对话及其所有消息。"""
        gen = self._aget_session()
        session = await anext(gen)
        try:
            # 先删检查点与消息，再删对话本身，避免留下孤儿记录。
            from sqlalchemy import delete
            await session.execute(
                delete(ConversationContextCheckpointModel).where(
                    ConversationContextCheckpointModel.conversation_id == conversation_id
                )
            )
            await session.execute(
                delete(ConversationMessageModel).where(
                    ConversationMessageModel.conversation_id == conversation_id
                )
            )
            # 再删对话
            result = await session.execute(
                delete(ConversationModel).where(
                    ConversationModel.conversation_id == conversation_id
                )
            )
            await session.commit()
            return result.rowcount > 0
        except Exception:
            await session.rollback()
            return False
        finally:
            await gen.aclose()

    def delete(self, conversation_id: str) -> bool:
        """同步删除 (使用 run_async 桥接)。"""
        try:
            return run_async(self.adelete(conversation_id))
        except Exception:
            return False


# ---- Singleton ----

_conv_repo: ConversationRepository | None = None


def get_conversation_repo() -> ConversationRepository:
    global _conv_repo
    if _conv_repo is None:
        _conv_repo = ConversationRepository()
    return _conv_repo
