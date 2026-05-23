"""Preference API — 用户偏好 REST 端点。

封装已有的 PreferenceMemory / PG 持久化能力，供 Android 客户端读写。
"""

from fastapi import APIRouter

from app.schemas.preference import PreferenceUpdate
from app.memory.preference_memory import get_memory
from app.repositories.pg_preference_repo import get_preference_repo

router = APIRouter()


@router.get("/api/preferences")
async def get_preferences(session_id: str):
    mem = get_memory()
    prefs = mem.get(session_id)
    return {"session_id": session_id, "preferences": prefs}


@router.put("/api/preferences")
async def update_preferences(session_id: str, req: PreferenceUpdate):
    mem = get_memory()
    stored = mem.get(session_id)
    if not stored:
        stored = {}

    data = {k: v for k, v in req.model_dump().items() if v is not None and v != []}
    if data:
        stored.update(data)
        # 同步更新内存缓存，避免下次 GET 读到旧数据
        mem._sessions[session_id] = stored
        # 持久化到 PG（如果启用）
        pref_repo = get_preference_repo()
        pref_repo.update(session_id, stored)

    return {"session_id": session_id, "preferences": stored}


@router.delete("/api/preferences")
async def reset_preferences(session_id: str):
    mem = get_memory()
    mem.forget(session_id)
    return {"ok": True, "session_id": session_id}


# ---- V2: Long-Term Preference Memory ----

@router.get("/api/preferences/long-term/{user_id}")
async def get_long_term_profile(user_id: str):
    """获取用户的长期偏好画像（跨会话学习结果）"""
    from app.memory.long_term import get_long_term_memory
    ltm = get_long_term_memory()
    profile = await ltm.get_profile(user_id)
    return profile.to_storable()


@router.delete("/api/preferences/long-term/{user_id}")
async def reset_long_term_profile(user_id: str):
    """重置用户的长期偏好画像"""
    from app.memory.long_term import get_long_term_memory
    ltm = get_long_term_memory()
    ltm.forget(user_id)
    return {"ok": True, "user_id": user_id}
