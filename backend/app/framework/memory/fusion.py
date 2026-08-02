"""记忆多路融合策略（移植 amap ``libs/memory_bank/recall/fusion.py`` 的 RRF）。

- :class:`RRFFusion`：Reciprocal Rank Fusion，各路按 score 排名后 ``1/(k+rank)`` 求和，
  归一化到 [0,1]。名称含 ``bm25`` 的路径先做 Sigmoid 归一化再排名。
  OmniCart 默认 ``score_threshold=0.0``（条目数少，不过滤），与 amap 的 0.55 不同。
- :class:`SimpleMergeFusion`：按 score 合并去重。
"""

from __future__ import annotations

import math

from app.framework.memory.protocols import MemoryItem


class RRFFusion:
    """RRF 融合策略。"""

    def __init__(self, *, rrf_k: int = 60, score_threshold: float = 0.0) -> None:
        self._rrf_k = rrf_k
        self._score_threshold = score_threshold

    def fuse(self, path_results: dict[str, list[MemoryItem]]) -> list[MemoryItem]:
        pool: dict[str, dict] = {}
        for path_name, items in path_results.items():
            is_bm25 = "bm25" in path_name.lower()
            for item in items:
                if not item.memory_id:
                    continue
                mid = item.memory_id
                entry = pool.setdefault(mid, {"item": item, "embedding": list(item.embedding), "path_scores": {}})
                raw = float(item.score or 0.0)
                score = self._bm25_sigmoid(raw) if is_bm25 else raw
                prev = entry["path_scores"].get(path_name)
                if prev is None or score > prev:
                    entry["path_scores"][path_name] = score
                if not entry["embedding"] and item.embedding:
                    entry["embedding"] = list(item.embedding)

        if not pool:
            return []

        # 各路独立排名
        all_paths: set[str] = set()
        for info in pool.values():
            all_paths.update(info["path_scores"].keys())
        path_ranks: dict[str, dict[str, int]] = {}
        for pname in all_paths:
            scored = [(mid, info["path_scores"][pname]) for mid, info in pool.items() if pname in info["path_scores"]]
            scored.sort(key=lambda x: x[1], reverse=True)
            path_ranks[pname] = {mid: i + 1 for i, (mid, _) in enumerate(scored)}

        # RRF 求和
        rrf: dict[str, float] = {}
        for mid in pool:
            rrf[mid] = sum(1.0 / (self._rrf_k + ranks[mid]) for ranks in path_ranks.values() if mid in ranks)

        max_rrf = max(rrf.values()) if rrf else 0.0
        if max_rrf == 0.0:
            return []

        result: list[MemoryItem] = []
        for mid, raw_rrf in rrf.items():
            final = raw_rrf / max_rrf
            if final < self._score_threshold:
                continue
            info = pool[mid]
            original = info["item"]
            result.append(
                MemoryItem(
                    memory_id=mid,
                    text=original.text,
                    score=final,
                    embedding=info["embedding"],
                    memory_type=original.memory_type,
                    extra=dict(original.extra),
                )
            )
        result.sort(key=lambda m: m.score, reverse=True)
        return result

    @staticmethod
    def _bm25_sigmoid(raw: float, k: float = 10.0, b: float = 0.5) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-k * (raw - b)))
        except OverflowError:
            return 0.0 if raw < b else 1.0


class SimpleMergeFusion:
    """按 score 合并去重（单路或已打分场景）。"""

    def __init__(self, *, score_threshold: float = 0.0) -> None:
        self._score_threshold = score_threshold

    def fuse(self, path_results: dict[str, list[MemoryItem]]) -> list[MemoryItem]:
        pool: dict[str, MemoryItem] = {}
        for items in path_results.values():
            for item in items:
                if not item.memory_id:
                    continue
                if item.memory_id not in pool or item.score > pool[item.memory_id].score:
                    pool[item.memory_id] = item
        result = sorted(pool.values(), key=lambda m: m.score, reverse=True)
        if self._score_threshold > 0:
            result = [m for m in result if m.score >= self._score_threshold]
        return result
