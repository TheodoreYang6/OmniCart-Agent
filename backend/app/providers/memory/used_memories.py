"""把 MemoryBank 长期偏好召回结果转换为 scoring 消费的 used_memories 结构。

对齐 spec §四「Router 里的 used_memories 注入改为 MemoryBank.recall() 结果，
scoring 的 preference_bonus/avoid_penalty 继续消费（字段兼容）」。

安全性：仅当用户有长期偏好条目时才产出（评测 demo 用户通常无条目 → used_memories 为空
→ 评分不变）；scoring 中 preference_bonus / avoid_penalty 均有上限（±0.10），影响有界。
"""

from __future__ import annotations

import logging

from app.framework.memory import MemoryRecallRequest

logger = logging.getLogger(__name__)


async def recall_used_memories(
    *,
    user_id: str,
    query: str,
    category: str = "",
    conversation_id: str = "",
    top_n: int = 10,
) -> list[dict]:
    """召回长期偏好并展开为 used_memories（brand / category / scenario / negative_preference）。"""
    if not user_id:
        return []

    from app.providers.memory import get_memory_bank  # 延迟导入，避免包循环

    request = MemoryRecallRequest(
        user_id=user_id,
        query=query,
        category=category,
        top_n=top_n,
        metadata={"conversation_id": conversation_id},
    )
    items = await get_memory_bank().recall_items(request, include={"preference"})

    used: list[dict] = []
    for item in items:
        entry = item.extra.get("entry", {}) or {}
        conf = float(item.score) if item.score else 0.6
        mid = item.memory_id or entry.get("entry_id", "")
        for brand in entry.get("brands", []) or []:
            used.append(_mem(mid, "brand", {"brand": brand}, conf, f"偏好品牌 {brand}"))
        cat = entry.get("category", "")
        if cat:
            used.append(_mem(mid, "category", {"category": cat}, conf, f"偏好品类 {cat}"))
        for scenario in entry.get("scenarios", []) or []:
            used.append(_mem(mid, "scenario", {"scenario": scenario}, conf, f"偏好场景 {scenario}"))
        for avoid in entry.get("avoid_tags", []) or []:
            used.append(_mem(mid, "negative_preference", {"avoid": avoid}, conf, f"避雷 {avoid}"))
    return used


def _mem(memory_id: str, memory_type: str, structured_value: dict, confidence: float, content: str) -> dict:
    return {
        "memory_id": memory_id,
        "memory_type": memory_type,
        "structured_value": structured_value,
        "confidence": confidence,
        "content": content,
    }
