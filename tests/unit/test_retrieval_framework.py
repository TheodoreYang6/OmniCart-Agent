"""RAG 检索框架单测（framework.retrieval）。

纯框架逻辑测试：注册表、融合策略、编排器的双超时/required 降级/分阶段调度。
不依赖任何外部服务或重量级依赖，用 fake RecallSource 驱动。
"""

from __future__ import annotations

import asyncio

import pytest

from app.framework.retrieval import (
    STAGE_ENRICH,
    STAGE_FALLBACK,
    STAGE_RECALL,
    RecallSource,
    RetrievalOrchestrator,
    RetrievalQuery,
    RetrievalResult,
    RequiredSourceError,
    RRFFusion,
    SequentialFusion,
    SourceRegistry,
)


# ---- fake 召回源 ----

class _Semantic(RecallSource):
    name = "semantic"
    priority = 10
    is_required = False
    stage = STAGE_RECALL

    async def search(self, query):
        return RetrievalResult(
            self.name,
            products=[
                {"product_id": "P1", "score": 0.9},
                {"product_id": "P2", "score": 0.5},
            ],
            evidence=[{"evidence_id": "E-MKT-P1", "source_type": "text_retrieval"}],
        )


class _SlowRequired(RecallSource):
    name = "slow"
    priority = 20
    is_required = False
    stage = STAGE_RECALL
    latency_budget_ms = 30  # per-source 熔断

    async def search(self, query):
        await asyncio.sleep(1.0)
        return RetrievalResult(self.name, products=[{"product_id": "PX", "score": 1.0}])


class _Supplementary(RecallSource):
    name = "supplementary"
    priority = 30
    stage = STAGE_FALLBACK

    async def search(self, query):
        return RetrievalResult(
            self.name,
            products=[{"product_id": "P3", "score": 0.3}],
            evidence=[{"evidence_id": "E-SUPP-P3"}],
        )


class _Review(RecallSource):
    name = "review"
    priority = 40
    stage = STAGE_ENRICH

    async def search(self, query):
        ev = [
            {"evidence_id": f"R-{p['product_id']}-0", "source_type": "review_positive"}
            for p in query.seed_products
        ]
        return RetrievalResult(self.name, evidence=ev)


def _builtin():
    return [_Semantic(), _SlowRequired(), _Supplementary(), _Review()]


# ---- 注册表 ----

def test_registry_priority_and_dedup():
    reg = SourceRegistry.default(builtin=_builtin)
    assert reg.names() == ["semantic", "slow", "supplementary", "review"]
    assert [s.name for s in reg.by_stage(STAGE_RECALL)] == ["semantic", "slow"]
    assert [s.name for s in reg.by_stage(STAGE_FALLBACK)] == ["supplementary"]


def test_registry_include_whitelist():
    reg = SourceRegistry.default(builtin=_builtin, include={"semantic"})
    assert reg.names() == ["semantic"]


# ---- 融合 ----

def test_sequential_fusion_preserves_order_and_dedup():
    fusion = SequentialFusion()
    r1 = RetrievalResult("a", products=[{"product_id": "P1", "score": 0.2}, {"product_id": "P2"}])
    r2 = RetrievalResult("b", products=[{"product_id": "P2"}, {"product_id": "P3"}])
    merged = fusion.fuse([r1, r2])
    assert [p["product_id"] for p in merged] == ["P1", "P2", "P3"]


def test_rrf_fusion_ranks_by_reciprocal_rank():
    fusion = RRFFusion(k=60)
    # P2 在两路都是 rank-1 → RRF 分严格最高
    r1 = RetrievalResult("a", products=[{"product_id": "P2", "score": 0.9}, {"product_id": "P1", "score": 0.5}])
    r2 = RetrievalResult("b", products=[{"product_id": "P2", "score": 0.8}, {"product_id": "P3", "score": 0.4}])
    merged = fusion.fuse([r1, r2])
    assert merged[0]["product_id"] == "P2"
    assert all("rrf_score" in p for p in merged)


# ---- 编排器 ----

@pytest.mark.asyncio
async def test_orchestrator_full_pipeline():
    """recall(2件) < min_results(3) → fallback 兜底；slow 源超时降级；enrich 读 seed_products。"""
    orch = RetrievalOrchestrator(SourceRegistry.default(builtin=_builtin), time_budget_ms=3000)
    bundle = await orch.retrieve(RetrievalQuery(query="蓝牙耳机", top_k=10, min_results=3))

    assert [p["product_id"] for p in bundle.products] == ["P1", "P2", "P3"]
    assert "slow" in bundle.dropped_sources

    eids = {e["evidence_id"] for e in bundle.evidence}
    assert {"E-MKT-P1", "E-SUPP-P3", "R-P1-0", "R-P2-0", "R-P3-0"} <= eids


@pytest.mark.asyncio
async def test_orchestrator_no_fallback_when_enough():
    """recall 已达 min_results → 不触发 fallback。"""

    class _Rich(RecallSource):
        name = "rich"
        priority = 10
        stage = STAGE_RECALL

        async def search(self, query):
            return RetrievalResult(
                self.name,
                products=[{"product_id": f"R{i}", "score": 1.0 - i * 0.1} for i in range(5)],
            )

    reg = SourceRegistry()
    reg.register(_Rich())
    reg.register(_Supplementary())
    orch = RetrievalOrchestrator(reg)
    bundle = await orch.retrieve(RetrievalQuery(query="x", top_k=10, min_results=3))
    assert "P3" not in [p["product_id"] for p in bundle.products]  # supplementary(P3) 未触发
    assert len(bundle.products) == 5


@pytest.mark.asyncio
async def test_orchestrator_required_source_raises():
    class _Bad(RecallSource):
        name = "semantic"
        priority = 10
        is_required = True
        stage = STAGE_RECALL

        async def search(self, query):
            raise RuntimeError("qdrant down")

    reg = SourceRegistry()
    reg.register(_Bad())
    orch = RetrievalOrchestrator(reg)
    with pytest.raises(RequiredSourceError):
        await orch.retrieve(RetrievalQuery(query="x"))


@pytest.mark.asyncio
async def test_orchestrator_top_k_truncation():
    class _Many(RecallSource):
        name = "many"
        priority = 10
        stage = STAGE_RECALL

        async def search(self, query):
            return RetrievalResult(
                self.name,
                products=[{"product_id": f"P{i}", "score": 1.0} for i in range(20)],
            )

    reg = SourceRegistry()
    reg.register(_Many())
    orch = RetrievalOrchestrator(reg)
    bundle = await orch.retrieve(RetrievalQuery(query="x", top_k=5, min_results=3))
    assert len(bundle.products) == 5


def test_effective_query_prefers_rewritten():
    q = RetrievalQuery(query="原始")
    assert q.effective_query == "原始"
    q.rewritten_query = "改写 关键词"
    assert q.effective_query == "改写 关键词"


# ---- 标准库 runner（无 pytest 时也能自检核心逻辑）----

if __name__ == "__main__":
    test_registry_priority_and_dedup()
    test_registry_include_whitelist()
    test_sequential_fusion_preserves_order_and_dedup()
    test_rrf_fusion_ranks_by_reciprocal_rank()
    test_effective_query_prefers_rewritten()
    asyncio.run(test_orchestrator_full_pipeline())
    asyncio.run(test_orchestrator_no_fallback_when_enough())
    asyncio.run(test_orchestrator_top_k_truncation())
    try:
        asyncio.run(test_orchestrator_required_source_raises())
        raise SystemExit("FAIL: required error not raised")
    except RequiredSourceError:
        pass
    print("ALL_RETRIEVAL_TESTS_OK")
