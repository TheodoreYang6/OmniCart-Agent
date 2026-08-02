"""内置召回路径（借鉴 amap ``libs/memory_bank/recall/paths.py`` 的 Vector/BM25/Tag）。

OmniCart 的偏好记忆是**结构化条目**（无稠密向量），因此内置两路轻量、无外部依赖的路径，
在候选条目集合上打分。候选由 Provider 通过 ``request.metadata["candidates"]`` 注入
（一次加载、多路复用），路径彼此无副作用（各自产出带独立 score 的 MemoryItem 副本）。

- :class:`TagPath`：标签/关键词重合度（Dice 系数）+ 品类命中基线分。
- :class:`RecencyPath`：按更新时间新旧排名衰减打分。
"""

from __future__ import annotations

from app.framework.memory.protocols import MemoryItem, MemoryRecallRequest


def _candidates(request: MemoryRecallRequest) -> list[MemoryItem]:
    cands = request.metadata.get("candidates")
    return list(cands) if cands else []


def _copy_with_score(item: MemoryItem, score: float) -> MemoryItem:
    return MemoryItem(
        memory_id=item.memory_id,
        text=item.text,
        score=score,
        embedding=list(item.embedding),
        memory_type=item.memory_type,
        extra=item.extra,
    )


class TagPath:
    """标签重合度召回路径。"""

    name = "tag"

    def __init__(self, *, base_score: float = 0.3) -> None:
        self._base = base_score

    async def retrieve(self, request: MemoryRecallRequest) -> list[MemoryItem]:
        signal = {t.lower() for t in (request.tags or []) if t}
        signal |= {w.lower() for w in (request.query or "").split() if len(w) >= 2}

        out: list[MemoryItem] = []
        for item in _candidates(request):
            tags = {str(t).lower() for t in item.extra.get("tags", []) if t}
            if signal and tags:
                inter = len(signal & tags)
                dice = 2.0 * inter / (len(signal) + len(tags))
            else:
                dice = 0.0
            out.append(_copy_with_score(item, self._base + dice))
        return out


class RecencyPath:
    """时间新旧召回路径（更新越新分越高）。"""

    name = "recency"

    async def retrieve(self, request: MemoryRecallRequest) -> list[MemoryItem]:
        cands = _candidates(request)
        ordered = sorted(cands, key=lambda it: str(it.extra.get("timestamp", "")), reverse=True)
        return [_copy_with_score(item, 1.0 / (1 + rank)) for rank, item in enumerate(ordered)]
