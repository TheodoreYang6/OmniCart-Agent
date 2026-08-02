"""内置上下文 Provider —— 时间 / 追问 / 长期偏好。

平移自现有分散逻辑，统一为 ContextManager 可并行采集的 ContextProvider：
- :class:`TimeContextProvider`：当前时间（新鲜度）。
- :class:`FollowUpContextProvider`：FollowUpEngine 产出的追问上下文（经 trigger 透传）。
- :class:`ProfileHintContextProvider`：长期偏好命中提示（复用 user_profile_service，
  其内部已由 MemoryBank 多路召回驱动）。
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.framework.context import ContextProvider, ContextSlice, ContextTrigger
from app.framework.registry import component

logger = logging.getLogger(__name__)

_WEEKDAY = "一二三四五六日"


@component(kind="context_provider", name="time", priority=5)
class TimeContextProvider(ContextProvider):
    """当前时间上下文。"""

    name = "time"
    priority = 5
    max_latency_ms = 100

    async def fetch(self, trigger: ContextTrigger) -> ContextSlice:
        now = datetime.now()
        text = f"[当前时间] {now.strftime('%Y-%m-%d %H:%M')} 周{_WEEKDAY[now.weekday()]}"
        return ContextSlice(self.name, content={"now": now.isoformat()}, formatted_text=text, priority=self.priority)


@component(kind="context_provider", name="followup", priority=10)
class FollowUpContextProvider(ContextProvider):
    """追问上下文（FollowUpEngine 输出，经 trigger.metadata['context_prompt'] 透传）。"""

    name = "followup"
    priority = 10
    max_latency_ms = 100

    def should_activate(self, trigger: ContextTrigger) -> bool:
        return bool(trigger.metadata.get("context_prompt"))

    async def fetch(self, trigger: ContextTrigger) -> ContextSlice:
        text = str(trigger.metadata.get("context_prompt", "") or "")
        return ContextSlice(self.name, formatted_text=text, priority=self.priority)


@component(kind="context_provider", name="visual", priority=8)
class VisualContextProvider(ContextProvider):
    """视觉识别结果上下文（拍照识图，经 trigger.metadata['visual_result'] 透传）。"""

    name = "visual"
    priority = 8
    max_latency_ms = 100

    def should_activate(self, trigger: ContextTrigger) -> bool:
        return bool(trigger.metadata.get("visual_result"))

    async def fetch(self, trigger: ContextTrigger) -> ContextSlice:
        vr = trigger.metadata.get("visual_result") or {}
        parts = []
        if vr.get("product_name"):
            parts.append(f"商品={vr['product_name']}")
        if vr.get("brand"):
            parts.append(f"品牌={vr['brand']}")
        if vr.get("category"):
            parts.append(f"品类={vr['category']}")
        text = f"[视觉识别] {', '.join(parts)}" if parts else ""
        return ContextSlice(self.name, content={"visual_result": vr}, formatted_text=text, priority=self.priority)


@component(kind="context_provider", name="profile_hint", priority=20)
class ProfileHintContextProvider(ContextProvider):
    """长期偏好命中上下文。"""

    name = "profile_hint"
    priority = 20
    max_latency_ms = 1500

    def should_activate(self, trigger: ContextTrigger) -> bool:
        return bool(trigger.user_id)

    async def fetch(self, trigger: ContextTrigger) -> ContextSlice:
        from app.services.user_profile_service import get_user_profile_service

        res = await get_user_profile_service().inject_profile_hints(trigger.user_id, trigger.query)
        hint = str(res.get("context_prompt", "") or "")
        return ContextSlice(
            self.name,
            content={"avoid_tags": res.get("avoid_tags", [])},
            formatted_text=hint,
            priority=self.priority,
        )
