"""偏好工具族（preference.*）—— 长期偏好的显式管理（Phase 6-B3）。

纯工具：不依赖会话快照，解析/合并/去重收敛在 UserProfileService + PreferenceWriter；
序号→entry_id 的引用解析由编排层（ShopActionAgent）完成。
"""

from __future__ import annotations

import logging

from app.framework.tools import Tool, ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

__all__ = ["PreferenceSaveTool", "PreferenceListTool", "PreferenceDeleteTool"]


class PreferenceSaveTool(Tool):
    spec = ToolSpec(
        name="preference.save",
        category="preference",
        permission="write",
        description="记住用户的长期偏好（如预算、忌口、避雷、品牌喜好），LLM 解析后合并入库",
        parameters={
            "type": "object",
            "properties": {"raw_text": {"type": "string", "description": "用户偏好原话"}},
            "required": ["raw_text"],
        },
    )

    async def run(self, ctx: ToolContext, raw_text: str = "") -> ToolResult:
        raw_text = (raw_text or "").strip()
        # P1-2: 剥句首触发词，避免“记住我”等前缀污染偏好解析
        for prefix in ("请记住", "帮我记住", "记住我", "记一下我", "记住"):
            if raw_text.startswith(prefix):
                raw_text = raw_text[len(prefix) :].lstrip("，, 的")
                break
        if not raw_text:
            return ToolResult(ok=False, message="想让我记住什么偏好呢？直接告诉我就好～")
        try:
            from app.services.user_profile_service import get_user_profile_service

            entry = await get_user_profile_service().parse_and_save(ctx.user_id, raw_text)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"preference.save failed: {e}")
            return ToolResult(ok=False, message="偏好保存失败，请稍后再试～")
        if not entry:
            return ToolResult(ok=False, message="这条我没太理解成偏好，换个说法试试？比如「以后推荐都控制在500以内」")
        summary = entry.get("raw_text") or raw_text
        return ToolResult(message=f"✅ 记住啦：「{summary[:50]}」，之后推荐都会考虑～", data={"entry": entry})


class PreferenceListTool(Tool):
    spec = ToolSpec(
        name="preference.list",
        category="preference",
        permission="read",
        description="列出用户已保存的长期偏好",
        parameters={
            "type": "object",
            "properties": {"category": {"type": "string", "description": "按品类过滤，可选"}},
        },
    )

    async def run(self, ctx: ToolContext, category: str = "") -> ToolResult:
        try:
            from app.services.user_profile_service import get_user_profile_service

            svc = get_user_profile_service()
            entries = (
                await svc.list_entries(ctx.user_id, category) if category else await svc.list_all_entries(ctx.user_id)
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"preference.list failed: {e}")
            return ToolResult(ok=False, message="暂时无法查看偏好，请稍后再试～")
        if not entries:
            return ToolResult(
                message="还没有记录过偏好哦～可以对我说「记住我预算都在500以内」这样的话", data={"entries": []}
            )
        lines = [f"💡 你的偏好（{len(entries)} 条）："]
        for idx, e in enumerate(entries, 1):
            text = (e.get("raw_text") or "")[:40]
            cat = e.get("category") or ""
            flag = "" if e.get("enabled", True) else "（已停用）"
            lines.append(f"  {idx}. [{cat}] {text}{flag}")
        lines.append("可以说「删除第N条偏好」来管理～")
        return ToolResult(message="\n".join(lines), data={"entries": entries})


class PreferenceDeleteTool(Tool):
    spec = ToolSpec(
        name="preference.delete",
        category="preference",
        permission="write",
        description="删除一条已保存的偏好",
        parameters={
            "type": "object",
            "properties": {"entry_id": {"type": "string"}},
            "required": ["entry_id"],
        },
    )

    async def run(self, ctx: ToolContext, entry_id: str = "") -> ToolResult:
        if not entry_id:
            return ToolResult(ok=False, message="请先说「我的偏好」看列表，再说「删除第N条偏好」～")
        try:
            from app.repositories.user_preference_repo import get_user_preference_repo

            ok = await get_user_preference_repo().adelete(entry_id, ctx.user_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"preference.delete failed: {e}")
            return ToolResult(ok=False, message="删除失败，请稍后再试～")
        if not ok:
            return ToolResult(ok=False, message="没找到这条偏好，可能已经删过了～")
        return ToolResult(message="🗑 已删除这条偏好～", data={"entry_id": entry_id})
