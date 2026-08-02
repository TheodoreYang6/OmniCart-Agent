"""记忆重排策略（移植 amap ``libs/memory_bank/recall/rerankers.py`` 的 MMR）。

- :class:`MMRReranker`：MMR 多样性重排 ``lambda*score - (1-lambda)*max_cos_sim``。
  候选无 embedding 时退化为按 score 输出 top_k（对偏好记忆等无向量场景友好）。
- :class:`NoopReranker`：直通。
"""

from __future__ import annotations

import math

from app.framework.memory.protocols import MemoryItem


class MMRReranker:
    """MMR 多样性重排。"""

    def __init__(self, *, top_k: int = 20, lambda_: float = 0.7) -> None:
        self._top_k = top_k
        self._lambda = lambda_

    def rerank(self, items: list[MemoryItem]) -> list[MemoryItem]:
        if len(items) <= 1:
            return items
        selected: list[MemoryItem] = []
        remaining = list(items)
        while remaining and len(selected) < self._top_k:
            best_idx, best_mmr = -1, -math.inf
            for idx, cand in enumerate(remaining):
                if selected and cand.embedding:
                    sims = [self._cosine(cand.embedding, s.embedding) for s in selected if s.embedding]
                    max_sim = max(sims) if sims else 0.0
                else:
                    max_sim = 0.0
                mmr = self._lambda * cand.score - (1.0 - self._lambda) * max_sim
                if mmr > best_mmr:
                    best_mmr, best_idx = mmr, idx
            if best_idx < 0:
                break
            selected.append(remaining.pop(best_idx))
        return selected

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        # 上面已保证等长 → strict 冗余；不用 zip(strict=) 以兼容 py39 dev-import 运行单测
        dot = sum(x * y for x, y in zip(a, b))  # noqa: B905
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)


class NoopReranker:
    """不重排 —— 直通。"""

    def rerank(self, items: list[MemoryItem]) -> list[MemoryItem]:
        return items
