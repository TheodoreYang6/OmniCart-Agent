"""Context 框架单测（framework.context）。

覆盖：TokenEstimator、TierSelector 分级、ContextManager 并行采集 + per-provider 超时降级 +
token 预算贪心裁剪。均用 fake ContextProvider / 纯数据驱动。
"""

from __future__ import annotations

import asyncio

import pytest

from app.framework.context import (
    CharTokenEstimator,
    ContextManager,
    ContextProvider,
    ContextSlice,
    ContextTrigger,
    Tier,
    TierSelector,
    TierThresholds,
)


class _StaticProvider(ContextProvider):
    def __init__(self, name, priority, text, max_latency_ms=1000):
        self.name = name
        self.priority = priority
        self.max_latency_ms = max_latency_ms
        self._text = text

    async def fetch(self, trigger):
        return ContextSlice(self.name, formatted_text=self._text, priority=self.priority)


class _SlowProvider(ContextProvider):
    name = "slow"
    priority = 1
    max_latency_ms = 30

    async def fetch(self, trigger):
        await asyncio.sleep(1.0)
        return ContextSlice("slow", formatted_text="x" * 500, priority=1)


# ---- TokenEstimator ----

def test_char_token_estimator_counts_cjk():
    est = CharTokenEstimator()
    assert est.estimate("") == 0
    assert est.estimate("中文四个字") == 5  # CJK 逐字
    assert est.estimate("abcdefgh") == 2  # 8 ascii / 4


# ---- TierSelector ----

def test_tier_selector_levels():
    sel = TierSelector(
        token_budget=100, thresholds=TierThresholds(0.6, 0.75, 0.9), estimator=CharTokenEstimator()
    )
    assert sel.select_by_ratio(0.3) == Tier.L0
    assert sel.select_by_ratio(0.65) == Tier.L1
    assert sel.select_by_ratio(0.8) == Tier.L2
    assert sel.select_by_ratio(0.95) == Tier.L3
    assert sel.select_by_ratio(1.5) == Tier.TRUNCATION


def test_tier_selector_rejects_bad_budget():
    with pytest.raises(ValueError):
        TierSelector(token_budget=0)


# ---- ContextManager ----

@pytest.mark.asyncio
async def test_context_manager_parallel_and_priority():
    mgr = ContextManager(
        [_StaticProvider("a", 20, "AAAA"), _StaticProvider("b", 10, "BBBB"), _SlowProvider()],
        token_budget=None,
        time_budget_ms=3000,
    )
    bundle = await mgr.assemble(ContextTrigger(query="q"))
    # slow 超时降级；其余按 priority 升序（b=10 在 a=20 前）
    assert [s.provider_name for s in bundle.slices] == ["b", "a"]
    assert "AAAA" in bundle.text and "BBBB" in bundle.text


@pytest.mark.asyncio
async def test_context_manager_token_budget_trims_low_priority():
    est = CharTokenEstimator()
    mgr = ContextManager(
        [_StaticProvider("keep", 10, "AAAA"), _StaticProvider("drop", 20, "B" * 400)],
        token_budget=est.estimate("AAAA") + 1,
    )
    bundle = await mgr.assemble(ContextTrigger(query="q"))
    assert [s.provider_name for s in bundle.slices] == ["keep"]
    assert "drop" in bundle.dropped


@pytest.mark.asyncio
async def test_context_manager_should_activate_filter():
    class _Gated(_StaticProvider):
        def should_activate(self, trigger):
            return trigger.user_id == "vip"

    mgr = ContextManager([_Gated("g", 10, "G")])
    assert (await mgr.assemble(ContextTrigger(query="q"))).slices == []
    assert (await mgr.assemble(ContextTrigger(query="q", user_id="vip"))).slices != []


@pytest.mark.asyncio
async def test_context_manager_include_providers_filter():
    # 供 compiler 消费 ContextBundle 时按名选取子集（spec §五）
    mgr = ContextManager([_StaticProvider("a", 10, "AA"), _StaticProvider("b", 20, "BB")])
    bundle = await mgr.assemble(ContextTrigger(query="q"), include_providers={"a"})
    assert [s.provider_name for s in bundle.slices] == ["a"]
    assert bundle.text == "AA"
