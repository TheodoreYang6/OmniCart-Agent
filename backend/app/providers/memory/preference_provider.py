"""长期偏好记忆 Provider + 写入整合器。

- :class:`PreferenceMemoryProvider`：把 ``user_preference_entries`` 条目作为候选，经
  ``DefaultRecallEngine``（TagPath + RecencyPath → RRF）做品类感知的多路召回排序。
  ``should_activate`` 要求 category 非空（无品类不召回，防跨品类污染，对齐现有保守策略）。
- :class:`PreferenceWriter`：写入前「读现有同品类条目 → 规则化语义整合（去重/冲突处理）」，
  替换旧的「每次新建条目、无去重」。冲突规则：同一品牌若新表述为避雷则从 must 移除、
  反之亦然（新表述胜出）。整合逻辑为纯函数，便于单测；如需可替换为 LLM 整合。
"""

from __future__ import annotations

import logging

from app.framework.memory import (
    DefaultRecallEngine,
    MemoryItem,
    MemoryProvider,
    MemoryRecallRequest,
    MemoryRecallResult,
    NoopReranker,
    RecencyPath,
    RRFFusion,
    TagPath,
)
from app.framework.registry import component

logger = logging.getLogger(__name__)


@component(kind="memory_provider", name="preference", priority=10)
class PreferenceMemoryProvider(MemoryProvider):
    """长期偏好召回 Provider。"""

    name = "preference"
    priority = 10

    def __init__(self) -> None:
        self._engine = DefaultRecallEngine(
            paths=[TagPath(), RecencyPath()],
            fusion=RRFFusion(),
            reranker=NoopReranker(),
            top_n=20,
        )

    def should_activate(self, request: MemoryRecallRequest) -> bool:
        # 品类感知：无 user_id 或未检测到品类 → 不召回（防止污染无关品类）
        return bool(request.user_id and request.category)

    async def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        from app.repositories.user_preference_repo import get_user_preference_repo

        repo = get_user_preference_repo()
        entries = await repo.alist_by_category(request.user_id, request.category)
        candidates = [self._entry_to_item(e.to_dict()) for e in entries]
        if not candidates:
            return MemoryRecallResult(self.name, items=[])
        request.metadata["candidates"] = candidates
        items = await self._engine.recall(request)
        return MemoryRecallResult(self.name, items=items)

    @staticmethod
    def _entry_to_item(entry: dict) -> MemoryItem:
        tags = list(entry.get("brands", [])) + list(entry.get("must_tags", [])) + list(entry.get("scenarios", []))
        return MemoryItem(
            memory_id=entry.get("entry_id", ""),
            text=entry.get("raw_text", ""),
            memory_type="preference",
            extra={
                "entry": entry,  # 原始条目，供 hints 构建复用
                "tags": tags,
                "timestamp": entry.get("updated_at", "") or entry.get("created_at", ""),
            },
        )


class PreferenceWriter:
    """偏好写入整合器 —— 读现有条目 → 规则化去重/冲突处理 → 落库。"""

    async def merge_and_save(self, user_id: str, raw_text: str, parsed: dict) -> dict | None:
        from app.repositories.user_preference_repo import get_user_preference_repo

        repo = get_user_preference_repo()
        category = parsed.get("category", "")
        existing = [e.to_dict() for e in await repo.alist_by_category(user_id, category)]
        target = self.find_mergeable(parsed, existing)

        if target:
            merged = self.merge(target, parsed)
            entry = await repo.asave(user_id, raw_text, merged, entry_id=target["entry_id"])
            logger.info("Preference merged into existing entry %s", target["entry_id"])
        else:
            entry = await repo.asave(user_id, raw_text, parsed)
        return entry.to_dict()

    # ---- 纯函数：可整合判定 + 合并（便于单测）----

    @staticmethod
    def find_mergeable(parsed: dict, existing: list[dict]) -> dict | None:
        """在同品类现有条目里找可整合目标：品牌有交集或子品类相同即视为同一偏好。"""
        category = parsed.get("category", "")
        if not category:
            return None
        new_brands = {str(b).lower() for b in parsed.get("brands", [])}
        new_sub = parsed.get("sub_category", "")
        for entry in existing:
            if entry.get("category", "") != category:
                continue
            old_brands = {str(b).lower() for b in entry.get("brands", [])}
            if new_brands and old_brands and (new_brands & old_brands):
                return entry
            if new_sub and new_sub == entry.get("sub_category", ""):
                return entry
        return None

    @staticmethod
    def merge(old: dict, new: dict) -> dict:
        """合并两条偏好，new 表述在冲突时胜出。"""

        def _union(key: str) -> list:
            seen: list = []
            for v in list(old.get(key, []) or []) + list(new.get(key, []) or []):
                if v not in seen:
                    seen.append(v)
            return seen

        must = _union("must_tags")
        avoid = _union("avoid_tags")
        new_avoid = {str(a).lower() for a in new.get("avoid_tags", [])}
        new_must = {str(m).lower() for m in new.get("must_tags", [])}
        # 冲突：新表述为避雷 → 从 must 移除；新表述为必备 → 从 avoid 移除
        must = [m for m in must if str(m).lower() not in new_avoid]
        avoid = [a for a in avoid if str(a).lower() not in new_must]

        return {
            "category": new.get("category") or old.get("category", ""),
            "sub_category": new.get("sub_category") or old.get("sub_category", ""),
            "brands": _union("brands"),
            "devices": _union("devices"),
            "scenarios": _union("scenarios"),
            "must_tags": must,
            "avoid_tags": avoid,
            "budget_min": new.get("budget_min") if new.get("budget_min") is not None else old.get("budget_min"),
            "budget_max": new.get("budget_max") if new.get("budget_max") is not None else old.get("budget_max"),
        }
