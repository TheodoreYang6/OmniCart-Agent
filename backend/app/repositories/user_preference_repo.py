"""UserPreferenceRepository — 独立偏好条目 PG 访问层。

每条偏好一个 entry_id，按 (user_id, category) 检索。
"""

import uuid
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_sync, run_async
from app.models.user_preference_entry import UserPreferenceEntry

_log = __import__("logging").getLogger(__name__)


class UserPreferenceRepository:

    # ---- Async internals ----

    @staticmethod
    async def _aget_session():
        factory = get_session_sync()
        if factory is None:
            raise RuntimeError("PostgreSQL is not configured")
        async with factory() as session:
            yield session

    async def _aget_by_entry_id(self, entry_id: str) -> Optional[UserPreferenceEntry]:
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(UserPreferenceEntry).where(UserPreferenceEntry.entry_id == entry_id)
            )
            return result.scalar_one_or_none()
        finally:
            await gen.aclose()

    # ---- 按品类查询 ----

    async def alist_by_category(
        self, user_id: str, category: str = "",
    ) -> list[UserPreferenceEntry]:
        """按品类获取用户的启用条目。category 为空则返回全部。"""
        if not user_id:
            return []
        gen = self._aget_session()
        session = await anext(gen)
        try:
            q = select(UserPreferenceEntry).where(
                UserPreferenceEntry.user_id == user_id,
                UserPreferenceEntry.enabled == True,
            )
            if category:
                # P1-2: “通用”偏好（全局预算/避雷等）全品类召回
                q = q.where(UserPreferenceEntry.category.in_([category, "通用"]))
            q = q.order_by(UserPreferenceEntry.created_at.desc())
            result = await session.execute(q)
            return list(result.scalars().all())
        finally:
            await gen.aclose()

    async def alist_all(
        self, user_id: str,
    ) -> list[UserPreferenceEntry]:
        """获取用户全部条目（含禁用），供管理界面使用。"""
        if not user_id:
            return []
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(UserPreferenceEntry)
                .where(UserPreferenceEntry.user_id == user_id)
                .order_by(UserPreferenceEntry.created_at.desc())
            )
            return list(result.scalars().all())
        finally:
            await gen.aclose()

    # ---- 写入 ----

    async def asave(
        self, user_id: str, raw_text: str, parsed: dict, entry_id: str = "",
    ) -> UserPreferenceEntry:
        """新建或更新一条偏好条目。entry_id 为空则新建，否则覆盖。"""
        gen = self._aget_session()
        session = await anext(gen)
        try:
            if entry_id:
                result = await session.execute(
                    select(UserPreferenceEntry).where(
                        UserPreferenceEntry.entry_id == entry_id,
                        UserPreferenceEntry.user_id == user_id,
                    )
                )
                entry = result.scalar_one_or_none()
                if entry:
                    for k, v in parsed.items():
                        if hasattr(entry, k) and v is not None:
                            setattr(entry, k, v)
                    entry.raw_text = raw_text
                    await session.commit()
                    await session.refresh(entry)
                    return entry

            # 新建
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            entry = UserPreferenceEntry(
                entry_id=entry_id or f"PREF-{uuid.uuid4().hex[:8]}",
                user_id=user_id,
                raw_text=raw_text,
                created_at=now,
                updated_at=now,
                **{k: v for k, v in parsed.items() if v is not None},
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry
        except Exception:
            await session.rollback()
            raise
        finally:
            await gen.aclose()

    # ---- 删除 ----

    async def adelete(self, entry_id: str, user_id: str) -> bool:
        if not entry_id or not user_id:
            return False
        gen = self._aget_session()
        session = await anext(gen)
        try:
            stmt = delete(UserPreferenceEntry).where(
                UserPreferenceEntry.entry_id == entry_id,
                UserPreferenceEntry.user_id == user_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
        except Exception:
            await session.rollback()
            return False
        finally:
            await gen.aclose()

    async def atoggle(self, entry_id: str, user_id: str, enabled: bool) -> bool:
        if not entry_id or not user_id:
            return False
        gen = self._aget_session()
        session = await anext(gen)
        try:
            result = await session.execute(
                select(UserPreferenceEntry).where(
                    UserPreferenceEntry.entry_id == entry_id,
                    UserPreferenceEntry.user_id == user_id,
                )
            )
            entry = result.scalar_one_or_none()
            if entry:
                entry.enabled = enabled
                await session.commit()
                return True
            return False
        except Exception:
            await session.rollback()
            return False
        finally:
            await gen.aclose()

    # ---- Sync wrappers ----

    def list_by_category(self, user_id: str, category: str = "") -> list[UserPreferenceEntry]:
        return run_async(self.alist_by_category(user_id, category))

    def list_all(self, user_id: str) -> list[dict]:
        entries = run_async(self.alist_all(user_id))
        return [e.to_dict() for e in entries]

    def save(self, user_id: str, raw_text: str, parsed: dict, entry_id: str = "") -> UserPreferenceEntry:
        return run_async(self.asave(user_id, raw_text, parsed, entry_id))

    def delete(self, entry_id: str, user_id: str) -> bool:
        return run_async(self.adelete(entry_id, user_id))

    def toggle(self, entry_id: str, user_id: str, enabled: bool) -> bool:
        return run_async(self.atoggle(entry_id, user_id, enabled))


# ---- Singleton ----

_repo: UserPreferenceRepository | None = None


def get_user_preference_repo() -> UserPreferenceRepository:
    global _repo
    if _repo is None:
        _repo = UserPreferenceRepository()
    return _repo
