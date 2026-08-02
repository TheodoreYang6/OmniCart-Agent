"""上下文编排器（借鉴 amap ``libs/context_store/manager.py``）。

多源并行采集（per-provider 超时 + 整体 time_budget）→ 格式化 + token 估算 →
按 priority 排序 → token 预算贪心裁剪（超预算丢弃低优先级切片）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.framework.context.protocols import (
    ContextBundle,
    ContextProvider,
    ContextSlice,
    ContextTrigger,
)
from app.framework.context.token_estimator import TokenEstimator, create_token_estimator

logger = logging.getLogger(__name__)

_UNSET: Any = object()


class ContextManager:
    """上下文编排器。"""

    def __init__(
        self,
        providers: list[ContextProvider],
        *,
        token_budget: int | None = None,
        time_budget_ms: int | None = 3000,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self._providers = providers
        self._token_budget = token_budget
        self._time_budget_ms = time_budget_ms
        self._estimator = estimator or create_token_estimator()

    @classmethod
    def default(
        cls,
        *,
        builtin: Any,
        include: set[str] | None = None,
        token_budget: int | None = None,
        time_budget_ms: int | None = 3000,
    ) -> ContextManager:
        """从 ``builtin()`` 清单装配。"""
        providers = [p for p in builtin() if include is None or p.name in include]
        return cls(providers, token_budget=token_budget, time_budget_ms=time_budget_ms)

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    async def assemble(
        self,
        trigger: ContextTrigger,
        *,
        token_budget: int | None | Any = _UNSET,
        include_providers: set[str] | None = None,
    ) -> ContextBundle:
        start = time.perf_counter()
        budget = self._token_budget if token_budget is _UNSET else token_budget

        active = [
            p
            for p in self._providers
            if p.should_activate(trigger) and (include_providers is None or p.name in include_providers)
        ]
        if not active:
            return ContextBundle()

        slices = await self._fetch_all(active, trigger)

        # 格式化 + token 估算
        by_name = {p.name: p for p in active}
        for s in slices:
            if not s.formatted_text and s.provider_name in by_name:
                s.formatted_text = by_name[s.provider_name].format_content(s)
            s.token_estimate = self._estimator.estimate(s.formatted_text)

        slices.sort(key=lambda s: s.priority)
        bundle = self._apply_budget(slices, budget)
        bundle.latency_ms = (time.perf_counter() - start) * 1000
        return bundle

    async def _fetch_all(self, providers: list[ContextProvider], trigger: ContextTrigger) -> list[ContextSlice]:
        tasks = {p.name: asyncio.create_task(self._fetch_one(p, trigger)) for p in providers}
        if self._time_budget_ms is not None:
            _, pending = await asyncio.wait(tasks.values(), timeout=self._time_budget_ms / 1000.0)
            for task in pending:
                task.cancel()
        else:
            await asyncio.gather(*tasks.values(), return_exceptions=True)

        out: list[ContextSlice] = []
        for name, task in tasks.items():
            if task.done() and not task.cancelled() and task.exception() is None:
                result = task.result()
                if result is not None:
                    out.append(result)
            else:
                logger.warning("context provider %r degraded (timeout/error)", name)
        return out

    async def _fetch_one(self, provider: ContextProvider, trigger: ContextTrigger) -> ContextSlice | None:
        try:
            return await asyncio.wait_for(provider.fetch(trigger), timeout=provider.max_latency_ms / 1000.0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("context provider %r fetch failed: %s", provider.name, exc)
            return None

    def _apply_budget(self, slices: list[ContextSlice], budget: int | None) -> ContextBundle:
        if budget is None:
            total = sum(s.token_estimate for s in slices)
            return ContextBundle(slices=slices, total_tokens=total)

        kept: list[ContextSlice] = []
        dropped: list[str] = []
        used = 0
        for s in slices:
            if used + s.token_estimate <= budget:
                kept.append(s)
                used += s.token_estimate
            else:
                dropped.append(s.provider_name)
        return ContextBundle(slices=kept, total_tokens=used, dropped=dropped)
