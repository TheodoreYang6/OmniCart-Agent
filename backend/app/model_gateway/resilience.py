"""模型调用弹性工具（借鉴 amap 多模型网关 SDK 的 retry/timeout/circuit_breaker 中间件）。

提供纯函数/类，供 ModelProvider 组合使用，把散落在各业务处的超时/重试收敛到一处：
- :func:`call_with_timeout`：整体超时。
- :func:`retry_async`：指数退避重试。
- :class:`CircuitBreaker`：连续失败熔断，冷却期直接快速失败，避免雪崩。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """熔断器打开期间拒绝调用。"""


async def call_with_timeout(coro: Awaitable[T], timeout_s: float | None) -> T:
    """给协程加整体超时；``timeout_s`` 为 None 时不限制。"""
    if timeout_s is None:
        return await coro
    return await asyncio.wait_for(coro, timeout_s)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 2,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """指数退避重试。attempts 为总尝试次数（含首次）。"""
    last_exc: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return await fn()
        except retry_on as exc:
            last_exc = exc
            if i == attempts - 1:
                break
            await asyncio.sleep(min(max_delay, base_delay * (2**i)))
    assert last_exc is not None
    raise last_exc


class CircuitBreaker:
    """连续失败熔断器。

    连续失败达到 ``fail_threshold`` 后打开，冷却 ``reset_timeout_s`` 秒内 ``allow()`` 返回
    False（快速失败）；冷却结束后重新放行。任一成功清零失败计数。
    """

    def __init__(self, *, fail_threshold: int = 5, reset_timeout_s: float = 30.0) -> None:
        self._threshold = fail_threshold
        self._reset = reset_timeout_s
        self._fails = 0
        self._open_until = 0.0

    def allow(self) -> bool:
        return not (self._open_until and time.monotonic() < self._open_until)

    def record_success(self) -> None:
        self._fails = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._fails += 1
        if self._fails >= self._threshold:
            self._open_until = time.monotonic() + self._reset

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        if not self.allow():
            raise CircuitOpenError("circuit breaker open")
        try:
            result = await fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result
