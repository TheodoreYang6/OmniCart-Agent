"""User Preference API — 独立条目管理端点。

每条偏好是一个独立条目 (entry_id)，按品类索引。
- GET  /api/preferences/entries         → 列出条目（可按品类筛选）
- PUT  /api/preferences/entries         → 新建或更新条目
- DELETE /api/preferences/entries/{id}  → 删除单条
- PUT  /api/preferences/entries/{id}/toggle → 启用/禁用
"""

import logging
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.user_profile_service import get_user_profile_service

_log = logging.getLogger(__name__)
router = APIRouter()


class EntrySaveRequest(BaseModel):
    user_id: str
    raw_text: str
    entry_id: str = ""  # 非空 = 覆盖旧条目


# ---- 列表 ----

@router.get("/api/preferences/entries")
async def list_entries(user_id: str = Query(default=""),
                       category: str = Query(default="")):
    """获取用户偏好条目。category 可选筛选品类。"""
    if not user_id:
        return {"entries": [], "count": 0}
    svc = get_user_profile_service()
    if category:
        entries = await svc.list_entries(user_id, category)
    else:
        entries = await svc.list_all_entries(user_id)
    return {"user_id": user_id, "entries": entries, "count": len(entries)}


# ---- 解析预览（不存库） ----

class ParseRequest(BaseModel):
    user_id: str
    raw_text: str


@router.post("/api/preferences/parse")
async def parse_preview(req: ParseRequest):
    """仅解析 raw_text，不写入数据库。供 Android 解析预览使用。"""
    if not req.user_id or not req.raw_text.strip():
        return {"ok": False, "error": "user_id and raw_text required"}
    svc = get_user_profile_service()
    parsed = await svc.parse_only(req.user_id, req.raw_text.strip())
    if parsed is None:
        return {"ok": False, "error": "解析失败，请检查输入内容是否包含明确品类"}
    return {"ok": True, "parsed": parsed}


# ---- 保存 ----

@router.put("/api/preferences/entries")
async def save_entry(req: EntrySaveRequest):
    """解析 raw_text 并保存为新条目（不合并旧条目）。entry_id 非空则覆盖。"""
    if not req.user_id or not req.raw_text.strip():
        return {"ok": False, "error": "user_id and raw_text required"}
    svc = get_user_profile_service()
    entry = await svc.parse_and_save(req.user_id, req.raw_text.strip(), req.entry_id)
    if entry is None:
        return {"ok": False, "error": "解析失败，请检查输入内容是否包含明确品类"}
    return {"ok": True, "entry": entry}


# ---- 删除 ----

@router.delete("/api/preferences/entries/{entry_id}")
async def delete_entry(entry_id: str, user_id: str = Query(default="")):
    """删除单条偏好条目。"""
    if not user_id or not entry_id:
        return {"ok": False}
    from app.repositories.user_preference_repo import get_user_preference_repo
    repo = get_user_preference_repo()
    deleted = await repo.adelete(entry_id, user_id)
    return {"ok": deleted}


# ---- 开关 ----

@router.put("/api/preferences/entries/{entry_id}/toggle")
async def toggle_entry(entry_id: str, user_id: str = Query(default=""),
                       enabled: bool = Query(default=True)):
    """启用/禁用单条偏好。"""
    if not user_id or not entry_id:
        return {"ok": False}
    from app.repositories.user_preference_repo import get_user_preference_repo
    repo = get_user_preference_repo()
    toggled = await repo.atoggle(entry_id, user_id, enabled)
    return {"ok": toggled, "enabled": enabled}


# ================================================================
# 兼容旧 API（过渡期，内部映射到新条目系统）
# ================================================================

@router.get("/api/preferences/profile")
async def get_profile(user_id: str = Query(default="")):
    """[已废弃] 获取用户偏好（合并所有条目为单 profile，兼容旧客户端）。

    旧 Android 期望 ProfileResponse 格式，此处将全部启用条目合并返回。"""
    if not user_id:
        return None
    svc = get_user_profile_service()
    entries = await svc.list_all_entries(user_id)
    enabled = [e for e in entries if e.get("enabled", True)]
    if not enabled:
        return None
    # 合并所有条目字段（union 去重）
    merged: dict = {"user_id": user_id, "enabled": True}
    for field in ("brands", "devices", "scenarios", "avoid_tags", "must_tags"):
        vals: set = set()
        for e in enabled:
            for v in (e.get(field) or []):
                vals.add(v)
        merged[field] = sorted(vals)
    # 品类取所有不重复
    cats: set = set()
    for e in enabled:
        c = e.get("category", "")
        if c:
            cats.add(c)
    merged["categories"] = sorted(cats)
    subs: set = set()
    for e in enabled:
        s = e.get("sub_category", "")
        if s:
            subs.add(s)
    merged["sub_categories"] = sorted(subs)
    # 预算取最宽范围
    mins = [e["budget_min"] for e in enabled if e.get("budget_min")]
    maxs = [e["budget_max"] for e in enabled if e.get("budget_max")]
    merged["budget_min"] = min(mins) if mins else None
    merged["budget_max"] = max(maxs) if maxs else None
    merged["raw_text"] = "\n".join(e.get("raw_text", "") for e in enabled)
    merged["updated_at"] = max(e.get("updated_at", "") for e in enabled)
    return merged


@router.put("/api/preferences/profile")
async def save_profile(req: EntrySaveRequest):
    """[已废弃] 保存偏好。现在每次调用创建一条独立条目，不再合并。

    返回 entry dict 以兼容旧 Android 客户端（期望 ProfileResponse 格式）。"""
    if not req.user_id or not req.raw_text.strip():
        return None
    svc = get_user_profile_service()
    entry = await svc.parse_and_save(req.user_id, req.raw_text.strip(), req.entry_id)
    return entry  # 直接返回 dict，兼容旧客户端


@router.delete("/api/preferences/profile")
async def reset_profile(user_id: str = Query(default="")):
    """[已废弃] 删除用户全部偏好条目。"""
    if not user_id:
        return {"ok": False}
    svc = get_user_profile_service()
    entries = await svc.list_all_entries(user_id)
    from app.repositories.user_preference_repo import get_user_preference_repo
    repo = get_user_preference_repo()
    for e in entries:
        await repo.adelete(e["entry_id"], user_id)
    return {"ok": True}


@router.put("/api/preferences/profile/toggle")
async def toggle_profile(user_id: str = Query(default=""), enabled: bool = Query(default=True)):
    """[已废弃] 批量开关全部条目。"""
    if not user_id:
        return {"ok": False}
    svc = get_user_profile_service()
    entries = await svc.list_all_entries(user_id)
    from app.repositories.user_preference_repo import get_user_preference_repo
    repo = get_user_preference_repo()
    for e in entries:
        await repo.atoggle(e["entry_id"], user_id, enabled)
    return {"ok": True, "enabled": enabled}


@router.delete("/api/preferences/profile/field")
async def delete_profile_field(user_id: str = Query(default=""),
                                field: str = Query(default=""),
                                value: str = Query(default="")):
    """[已废弃] 删除包含特定字段值的条目。"""
    if not user_id or not field or not value:
        return {"ok": False}
    svc = get_user_profile_service()
    entries = await svc.list_all_entries(user_id)
    from app.repositories.user_preference_repo import get_user_preference_repo
    repo = get_user_preference_repo()
    for e in entries:
        vals = e.get(field) or []
        if value in vals:
            await repo.adelete(e["entry_id"], user_id)
            return {"ok": True}
    return {"ok": False}
