"""默认召回引擎（借鉴 amap ``libs/memory_bank/recall/engine.py``）。

组装管线：``N 路并发(RetrievalPath) → Fusion → Rerank → top_n``。业务方既可整体替换
（自实现 recall()），也可细粒度替换其中的 paths / fusion / reranker。
"""

from __future__ import annotations

import asyncio
import logging

from app.framework.memory.fusion import RRFFusion
from app.framework.memory.protocols import (
    FusionStrategy,
    MemoryItem,
    MemoryRecallRequest,
    RerankStrategy,
    RetrievalPath,
)
from app.framework.memory.rerank import MMRReranker

logger = logging.getLogger(__name__)


class DefaultRecallEngine:
    """默认多路召回引擎。"""

    def __init__(
        self,
        *,
        paths: list[RetrievalPath],
        fusion: FusionStrategy | None = None,
        reranker: RerankStrategy | None = None,
        top_n: int = 20,
        timeout_ms: int = 3000,
    ) -> None:
        self._paths = paths
        self._fusion: FusionStrategy = fusion or RRFFusion()
        self._reranker: RerankStrategy = reranker or MMRReranker()
        self._top_n = top_n
        self._timeout_ms = timeout_ms

    async def recall(self, request: MemoryRecallRequest) -> list[MemoryItem]:
        path_results = await self._execute_paths(request)
        merged = self._fusion.fuse(path_results)
        reranked = self._reranker.rerank(merged)
        top_n = request.top_n or self._top_n
        return reranked[:top_n]

    async def _execute_paths(self, request: MemoryRecallRequest) -> dict[str, list[MemoryItem]]:
        if not self._paths:
            return {}
        tasks = {p.name: asyncio.create_task(p.retrieve(request)) for p in self._paths}
        _, pending = await asyncio.wait(tasks.values(), timeout=self._timeout_ms / 1000.0)
        for task in pending:
            task.cancel()

        results: dict[str, list[MemoryItem]] = {}
        for name, task in tasks.items():
            if task.done() and not task.cancelled() and task.exception() is None:
                results[name] = task.result()
            else:
                if task.done() and not task.cancelled() and task.exception() is not None:
                    logger.warning("memory path %r failed: %s", name, task.exception())
                results[name] = []
        return results
