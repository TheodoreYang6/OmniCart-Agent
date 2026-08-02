"""Memory 框架单测（framework.memory + providers.memory 纯逻辑）。

覆盖：RRF/SimpleMerge 融合、MMR 重排、DefaultRecallEngine、MemoryBank 并行召回 +
include 白名单，以及 PreferenceWriter 的去重/冲突整合纯逻辑。均用 fake / 纯数据驱动。
"""

from __future__ import annotations

import pytest

from app.framework.memory import (
    DefaultRecallEngine,
    MemoryBank,
    MemoryItem,
    MemoryProvider,
    MemoryRecallRequest,
    MemoryRecallResult,
    MMRReranker,
    NoopReranker,
    RecencyPath,
    RRFFusion,
    SimpleMergeFusion,
    TagPath,
)
from app.providers.memory.preference_provider import PreferenceWriter


def _item(mid, score=0.0, emb=None):
    return MemoryItem(mid, text=mid, score=score, embedding=emb or [])


# ---- 融合 ----

def test_rrf_fusion_combines_paths():
    fusion = RRFFusion()
    path_results = {
        "tag": [_item("M1", 0.9), _item("M2", 0.3)],
        "recency": [_item("M2", 1.0), _item("M1", 0.5)],
    }
    merged = fusion.fuse(path_results)
    assert {m.memory_id for m in merged} == {"M1", "M2"}
    assert all(0.0 <= m.score <= 1.0 for m in merged)


def test_simple_merge_fusion_takes_max_score():
    fusion = SimpleMergeFusion()
    merged = fusion.fuse({"a": [_item("M1", 0.3)], "b": [_item("M1", 0.9), _item("M2", 0.2)]})
    by_id = {m.memory_id: m.score for m in merged}
    assert by_id["M1"] == 0.9
    assert merged[0].memory_id == "M1"


# ---- 重排 ----

def test_mmr_prefers_diversity():
    # A、B 近似重复（同向量），C 多样；MMR 应在 A 之后优先选 C
    items = [
        _item("A", 0.9, [1.0, 0.0]),
        _item("B", 0.85, [1.0, 0.0]),
        _item("C", 0.8, [0.0, 1.0]),
    ]
    out = MMRReranker(top_k=3, lambda_=0.7).rerank(items)
    assert out[0].memory_id == "A"
    assert out[1].memory_id == "C"  # 多样性胜过近似重复的 B


def test_noop_reranker_passthrough():
    items = [_item("A", 0.5), _item("B", 0.9)]
    assert NoopReranker().rerank(items) == items


# ---- RecallEngine + Paths ----

@pytest.mark.asyncio
async def test_recall_engine_tag_hit_ranks_first():
    cands = [
        MemoryItem("PREF-1", extra={"tags": ["索尼", "sony", "降噪"], "timestamp": "2026-01-01"}),
        MemoryItem("PREF-2", extra={"tags": ["漫步者"], "timestamp": "2026-01-02"}),
    ]
    engine = DefaultRecallEngine(
        paths=[TagPath(), RecencyPath()], fusion=RRFFusion(), reranker=NoopReranker()
    )
    req = MemoryRecallRequest(user_id="u", query="索尼 耳机", tags=["索尼"], top_n=10)
    req.metadata["candidates"] = cands
    items = await engine.recall(req)
    assert {i.memory_id for i in items} == {"PREF-1", "PREF-2"}


# ---- MemoryBank ----

class _FakeProvider(MemoryProvider):
    def __init__(self, name, items):
        self.name = name
        self._items = items

    async def recall(self, request):
        return MemoryRecallResult(self.name, items=self._items)


@pytest.mark.asyncio
async def test_memory_bank_recall_and_include():
    bank = MemoryBank.default(
        builtin_providers=[
            _FakeProvider("preference", [_item("P1", 1.0)]),
            _FakeProvider("short_term", [_item("S1", 1.0)]),
        ]
    )
    # 全部
    res = await bank.recall(MemoryRecallRequest(user_id="u"))
    assert set(res.keys()) == {"preference", "short_term"}
    # include 白名单
    items = await bank.recall_items(MemoryRecallRequest(user_id="u"), include={"preference"})
    assert [i.memory_id for i in items] == ["P1"]


@pytest.mark.asyncio
async def test_memory_bank_provider_error_isolated():
    class _Bad(MemoryProvider):
        name = "bad"

        async def recall(self, request):
            raise RuntimeError("boom")

    bank = MemoryBank(providers=[_Bad(), _FakeProvider("ok", [_item("X")])])
    res = await bank.recall(MemoryRecallRequest(user_id="u"))
    assert res["bad"].error is not None
    assert res["ok"].items[0].memory_id == "X"


# ---- PreferenceWriter 去重/冲突整合 ----

def test_preference_writer_find_mergeable():
    existing = [
        {"entry_id": "A", "category": "数码电子", "brands": ["索尼"], "sub_category": "真无线耳机"}
    ]
    assert PreferenceWriter.find_mergeable({"category": "数码电子", "brands": ["sony", "索尼"]}, existing)["entry_id"] == "A"
    assert PreferenceWriter.find_mergeable({"category": "数码电子", "sub_category": "真无线耳机"}, existing)["entry_id"] == "A"
    assert PreferenceWriter.find_mergeable({"category": "美妆护肤", "brands": ["索尼"]}, existing) is None
    assert PreferenceWriter.find_mergeable({"category": "数码电子", "brands": ["华为"], "sub_category": "手机"}, existing) is None


def test_preference_writer_merge_conflict_resolution():
    old = {
        "category": "数码电子", "sub_category": "真无线耳机", "brands": ["索尼"],
        "must_tags": ["降噪", "入耳"], "avoid_tags": [], "scenarios": ["通勤"], "budget_max": 500,
    }
    new = {
        "category": "数码电子", "brands": ["漫步者"], "must_tags": [],
        "avoid_tags": ["入耳"], "scenarios": ["运动"], "budget_max": 800,
    }
    m = PreferenceWriter.merge(old, new)
    assert set(m["brands"]) == {"索尼", "漫步者"}
    assert "入耳" not in m["must_tags"] and "降噪" in m["must_tags"]  # 新避雷覆盖旧必备
    assert "入耳" in m["avoid_tags"]
    assert set(m["scenarios"]) == {"通勤", "运动"}
    assert m["budget_max"] == 800  # 新值胜出
