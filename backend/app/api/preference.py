"""Preference API — 用户偏好 REST 端点 (Memory Lite)。

短期约束已合并到 context_snapshot (ConversationService 管理),
长期偏好待 P6 显式用户设置页面。
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.identity import Actor, resolve_actor
from app.repositories.conversation_repo import get_conversation_repo
from app.schemas.preference import PreferenceUpdate
from app.services.conversation_service import get_conversation_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _owned_conversation_id(actor: Actor, conversation_id: str, session_id: str) -> str | None:
    repo = get_conversation_repo()
    if conversation_id:
        conv = repo.get(conversation_id)
        return conversation_id if conv and conv.user_id == actor.user_id else None
    if session_id:
        conv = repo.get_latest_by_session(actor.user_id, session_id)
        return conv.conversation_id if conv else None
    return None


@router.get("/api/preferences")
async def get_preferences(session_id: str = Query(default=""),
                          conversation_id: str = Query(default=""),
                          actor: Actor = Depends(resolve_actor)):
    """获取当前会话偏好 (从 context_snapshot 读取)。"""
    prefs = {}
    cid = _owned_conversation_id(actor, conversation_id, session_id)
    if cid:
        try:
            svc = get_conversation_service()
            snapshot = svc.get_context_snapshot_sync(cid)
            if snapshot:
                prefs = dict(snapshot.get("constraints", {}))
        except Exception as e:
            logger.debug(f"Preferences read skipped: {e}")

    return {"session_id": cid, "preferences": prefs}


@router.put("/api/preferences")
async def update_preferences(session_id: str = Query(default=""),
                             conversation_id: str = Query(default=""),
                             req: PreferenceUpdate = None,
                             actor: Actor = Depends(resolve_actor)):
    """更新当前会话偏好 → 写入 context_snapshot (best-effort)。"""
    cid = _owned_conversation_id(actor, conversation_id, session_id)
    if not cid:
        raise HTTPException(status_code=404, detail="Conversation not found")

    data = {k: v for k, v in (req.model_dump() if req else {}).items()
            if v is not None and v != []}
    if not data:
        return {"session_id": cid, "preferences": {}}

    try:
        svc = get_conversation_service()
        snapshot = svc.get_context_snapshot_sync(cid)
        constraints = dict(snapshot.get("constraints", {}))
        constraints.update(data)
        svc.update_context_snapshot(cid, {"constraints": constraints})
        return {"session_id": cid, "preferences": constraints}
    except Exception as e:
        logger.debug(f"Preferences update skipped: {e}")
        return {"session_id": cid, "preferences": {}}


@router.delete("/api/preferences")
async def reset_preferences(session_id: str = Query(default=""),
                            conversation_id: str = Query(default=""),
                            actor: Actor = Depends(resolve_actor)):
    """重置当前会话偏好 (清空 context_snapshot 中的 constraints)。"""
    cid = _owned_conversation_id(actor, conversation_id, session_id)
    if not cid:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        svc = get_conversation_service()
        svc.update_context_snapshot(cid, {"constraints": {}, "current_turn": {}})
    except Exception as e:
        logger.debug(f"Preferences reset skipped: {e}")
    return {"ok": True, "session_id": cid}
