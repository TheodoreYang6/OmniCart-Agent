"""模型网关弹性工具单测（model_gateway.resilience）。纯逻辑，无外部依赖。"""

from __future__ import annotations

import asyncio

import pytest

from app.model_gateway.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    call_with_timeout,
    retry_async,
)


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert await retry_async(flaky, attempts=3, base_delay=0.001) == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_single_attempt_raises_immediately():
    calls = {"n": 0}

    async def always():
        calls["n"] += 1
        raise ValueError("v")

    with pytest.raises(ValueError):
        await retry_async(always, attempts=1)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_call_with_timeout():
    async def slow():
        await asyncio.sleep(1.0)
        return "x"

    with pytest.raises(asyncio.TimeoutError):
        await call_with_timeout(slow(), 0.02)

    async def fast():
        return "y"

    assert await call_with_timeout(fast(), None) == "y"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(fail_threshold=2, reset_timeout_s=100)

    async def boom():
        raise RuntimeError("e")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(boom)
    assert not cb.allow()
    with pytest.raises(CircuitOpenError):
        await cb.call(boom)


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets():
    cb = CircuitBreaker(fail_threshold=2, reset_timeout_s=0.0)

    async def ok():
        return 1

    assert await cb.call(ok) == 1
    assert cb.allow()
