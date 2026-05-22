"""偏好记忆仓库 — PostgreSQL 持久化 + 内存降级。"""

import asyncio
import logging
from typing import Optional

import nest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_session_sync
from app.models.user_preference import UserPreferenceModel

logger = logging.getLogger(__name__)
_nest_patched = False


class PgPreferenceRepository:
    """PostgreSQL 偏好记忆仓库。"""

    def _run(self, coro):
        global _nest_patched
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        if not _nest_patched:
            nest_asyncio.apply(loop)
            _nest_patched = True

        return loop.run_until_complete(coro)

    async def aget(self, session_id: str, user_id: str = "") -> dict:
        factory = get_session_sync()
        if factory is None:
            return {}
        async with factory() as session:
            result = await session.execute(
                select(UserPreferenceModel).where(
                    UserPreferenceModel.session_id == session_id,
                ).limit(1)
            )
            row = result.scalars().first()
            return row.preferences if row else {}

    async def aupdate(self, session_id: str, preferences: dict, user_id: str = ""):
        factory = get_session_sync()
        if factory is None:
            return
        async with factory() as session:
            stmt = pg_insert(UserPreferenceModel).values(
                session_id=session_id,
                user_id=user_id,
                preferences=preferences,
            ).on_conflict_do_update(
                constraint="uq_user_preferences_session_user",
                set_={"preferences": preferences},
            )
            await session.execute(stmt)
            await session.commit()

    async def aforget(self, session_id: str):
        factory = get_session_sync()
        if factory is None:
            return
        async with factory() as session:
            result = await session.execute(
                select(UserPreferenceModel).where(
                    UserPreferenceModel.session_id == session_id,
                )
            )
            row = result.scalars().first()
            if row:
                await session.delete(row)
                await session.commit()

    # ---- 同步接口 ----

    def get(self, session_id: str, user_id: str = "") -> dict:
        return self._run(self.aget(session_id, user_id))

    def update(self, session_id: str, preferences: dict, user_id: str = ""):
        self._run(self.aupdate(session_id, preferences, user_id))

    def forget(self, session_id: str):
        self._run(self.aforget(session_id))


class MemPreferenceRepository:
    """内存偏好记忆仓库 — V0 降级实现。"""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, session_id: str, user_id: str = "") -> dict:
        key = f"{session_id}:{user_id}"
        return self._store.get(key, {})

    def update(self, session_id: str, preferences: dict, user_id: str = ""):
        key = f"{session_id}:{user_id}"
        self._store[key] = preferences

    def forget(self, session_id: str):
        keys = [k for k in self._store if k.startswith(session_id)]
        for k in keys:
            del self._store[k]


# ---- 工厂 ----

_pref_repo: PgPreferenceRepository | MemPreferenceRepository | None = None


def get_preference_repo() -> PgPreferenceRepository | MemPreferenceRepository:
    global _pref_repo
    if _pref_repo is None:
        from app.core.config import USE_POSTGRES
        if USE_POSTGRES:
            _pref_repo = PgPreferenceRepository()
        else:
            _pref_repo = MemPreferenceRepository()
    return _pref_repo
