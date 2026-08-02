"""MemoryBank 统一入口（借鉴 amap ``libs/memory_bank/bank.py``）。

职责：可选 rewrite → 多 Provider 并行召回（受整体 time_budget 约束）→ 汇总。
``default(builtin_providers=...)`` 用显式清单装配（对齐 amap 的清单式发现）。
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.framework.memory.protocols import (
    MemoryItem,
    MemoryProvider,
    MemoryRecallRequest,
    MemoryRecallResult,
    QueryRewriter,
)

logger = logging.getLogger(__name__)


class MemoryBank:
    """记忆银行 —— 统一召回入口。"""

    def __init__(
        self,
        *,
        providers: list[MemoryProvider] | None = None,
        rewriter: QueryRewriter | None = None,
        time_budget_ms: int = 3000,
    ) -> None:
        self._providers = list(providers or [])
        self._rewriter = rewriter
        self._time_budget_ms = time_budget_ms

    @classmethod
    def default(
        cls,
        *,
        builtin_providers: list[MemoryProvider],
        include: set[str] | None = None,
        rewriter: QueryRewriter | None = None,
        time_budget_ms: int = 3000,
    ) -> MemoryBank:
        providers = [p for p in builtin_providers if include is None or p.name in include]
        logger.info("MemoryBank.default() providers: %s", [p.name for p in providers])
        return cls(providers=providers, rewriter=rewriter, time_budget_ms=time_budget_ms)

    def register(self, provider: MemoryProvider) -> None:
        self._providers.append(provider)

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    async def recall(
        self,
        request: MemoryRecallRequest,
        *,
        include: set[str] | None = None,
    ) -> dict[str, MemoryRecallResult]:
        """并行召回所有激活的 Provider，返回 {provider_name: result}。"""
        await self._apply_rewrite(request)
        active = [p for p in self._providers if p.should_activate(request) and (include is None or p.name in include)]
        if not active:
            return {}

        tasks = {p.name: asyncio.create_task(self._recall_one(p, request)) for p in active}
        _, pending = await asyncio.wait(tasks.values(), timeout=self._time_budget_ms / 1000.0)
        for task in pending:
            task.cancel()

        results: dict[str, MemoryRecallResult] = {}
        for name, task in tasks.items():
            if task.done() and not task.cancelled() and task.exception() is None:
                results[name] = task.result()
            else:
                results[name] = MemoryRecallResult(provider_name=name, error="timeout")
        return results

    async def recall_items(
        self,
        request: MemoryRecallRequest,
        *,
        include: set[str] | None = None,
    ) -> list[MemoryItem]:
        """便捷方法：汇总所有 Provider 的 items 为单一列表。"""
        results = await self.recall(request, include=include)
        items: list[MemoryItem] = []
        for res in results.values():
            items.extend(res.items)
        return items

    async def _apply_rewrite(self, request: MemoryRecallRequest) -> None:
        if self._rewriter is None:
            return
        try:
            rewritten = await self._rewriter.rewrite(request)
            if rewritten and rewritten.strip():
                request.query = rewritten
        except Exception:  # noqa: BLE001
            logger.warning("memory query rewrite failed, using original", exc_info=True)

    @staticmethod
    async def _recall_one(provider: MemoryProvider, request: MemoryRecallRequest) -> MemoryRecallResult:
        start = time.perf_counter()
        try:
            result = await provider.recall(request)
            result.latency_ms = (time.perf_counter() - start) * 1000
            return result
        except Exception as exc:  # noqa: BLE001
            return MemoryRecallResult(
                provider_name=provider.name,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
            )
