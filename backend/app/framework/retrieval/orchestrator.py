"""检索编排器（借鉴 amap ``libs/knowledge_base/orchestrator.py`` 的 6 阶段管线）。

管线阶段：

    ① Query Rewrite    改写查询（可插拔 QueryRewriter，失败回退原 query）
    ② Activation Filter 按 should_activate 激活筛选
    ③ Parallel Fetch    多源并行 + 双超时（per-source latency_budget_ms + 整体 time_budget）
    ④ Result Processing required 失败上抛 / optional 失败降级
    ⑤ Fusion            商品融合去重（SequentialFusion 默认 / RRFFusion 可选）
    ⑥ Post-process      fallback 兜底 + top_k 截断 + enrich 证据增强 + 打包

分三个阶段调度以复现现 retrieval_agent 的语义：recall（主召回）→ fallback（不足兜底）
→ enrich（证据增强，读 seed_products）。产出的 products / evidence 结构与现实现一致，
下游 Decision / Guard / Android 无感。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.framework.retrieval.errors import RequiredSourceError
from app.framework.retrieval.fusion import RetrievalFusion, SequentialFusion
from app.framework.retrieval.registry import SourceRegistry
from app.framework.retrieval.rewrite import QueryRewriter
from app.framework.retrieval.source import (
    STAGE_ENRICH,
    STAGE_FALLBACK,
    STAGE_RECALL,
    RecallSource,
)
from app.framework.retrieval.types import RetrievalBundle, RetrievalQuery, RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """RAG 检索编排器。"""

    def __init__(
        self,
        registry: SourceRegistry,
        *,
        rewriter: QueryRewriter | None = None,
        fusion: RetrievalFusion | None = None,
        time_budget_ms: int | None = 5000,
    ) -> None:
        self._registry = registry
        self._rewriter = rewriter
        self._fusion: RetrievalFusion = fusion or SequentialFusion()
        self._time_budget_ms = time_budget_ms

    async def retrieve(self, query: RetrievalQuery) -> RetrievalBundle:
        """执行完整检索管线，返回融合后的 RetrievalBundle。"""
        start = time.perf_counter()

        # ① Query Rewrite
        await self._apply_rewrite(query)

        dropped: list[str] = []
        per_source: dict[str, float] = {}

        # ②③④ recall 阶段：激活筛选 → 并行检索 → 处理
        recall_sources = self._active(STAGE_RECALL, query)
        recall_results, d1, l1 = await self._run_sources(recall_sources, query)
        dropped += d1
        per_source.update(l1)

        # ⑤ 融合商品 + 汇总证据
        products = self._fusion.fuse(recall_results)
        evidence = self._collect_evidence(recall_results)

        # ⑥a fallback：主召回不足时兜底（复现 `< min_results` 逻辑）
        if len(products) < query.min_results:
            fb_sources = self._active(STAGE_FALLBACK, query)
            fb_results, d2, l2 = await self._run_sources(fb_sources, query)
            dropped += d2
            per_source.update(l2)
            products = self._append_new(products, fb_results)
            evidence += self._collect_evidence(fb_results)

        # ⑥b top_k 截断
        products = products[: query.top_k]

        # ⑥c enrich：证据增强源读取已召回商品
        query.seed_products = products
        enrich_sources = self._active(STAGE_ENRICH, query)
        enrich_results, d3, l3 = await self._run_sources(enrich_sources, query)
        dropped += d3
        per_source.update(l3)
        evidence += self._collect_evidence(enrich_results)

        latency_ms = (time.perf_counter() - start) * 1000
        return RetrievalBundle(
            products=products,
            evidence=evidence,
            dropped_sources=dropped,
            per_source_latency_ms=per_source,
            latency_ms=latency_ms,
        )

    # ---- 内部 ----

    def _active(self, stage: str, query: RetrievalQuery) -> list[RecallSource]:
        return [s for s in self._registry.by_stage(stage) if s.should_activate(query)]

    async def _apply_rewrite(self, query: RetrievalQuery) -> None:
        if self._rewriter is None:
            return
        try:
            rewritten = await self._rewriter.rewrite(query)
            if rewritten and rewritten.strip():
                query.rewritten_query = rewritten
        except Exception:  # noqa: BLE001
            logger.warning("query rewrite failed, using original query", exc_info=True)

    async def _run_sources(
        self,
        sources: list[RecallSource],
        query: RetrievalQuery,
    ) -> tuple[list[RetrievalResult], list[str], dict[str, float]]:
        """并行执行一批源，受整体 time_budget 约束。

        Returns:
            (成功结果列表[按 priority 顺序], 被降级的源名列表, 各源耗时)。

        Raises:
            RequiredSourceError: 必需源失败/超时。
        """
        if not sources:
            return [], [], {}

        tasks: dict[str, asyncio.Task[RetrievalResult]] = {
            s.name: asyncio.create_task(self._search_one(s, query)) for s in sources
        }

        if self._time_budget_ms is not None:
            _, pending = await asyncio.wait(tasks.values(), timeout=self._time_budget_ms / 1000.0)
            for task in pending:
                task.cancel()
        else:
            await asyncio.gather(*tasks.values(), return_exceptions=True)

        results: list[RetrievalResult] = []
        dropped: list[str] = []
        latencies: dict[str, float] = {}

        # 按 sources 原顺序（priority 升序）收集，保证 SequentialFusion 拼接顺序稳定
        for source in sources:
            task = tasks[source.name]
            if task.done() and not task.cancelled() and task.exception() is None:
                res = task.result()
                latencies[source.name] = res.latency_ms
                if res.error:
                    if source.is_required:
                        raise RequiredSourceError(source.name, res.error)
                    dropped.append(source.name)
                else:
                    results.append(res)
            else:
                # 整体预算超时/取消，或未预期异常
                cause = "time_budget_exceeded"
                if task.done() and not task.cancelled():
                    cause = task.exception()
                if source.is_required:
                    raise RequiredSourceError(source.name, cause)
                dropped.append(source.name)
                logger.warning("recall source %r degraded: %s", source.name, cause)

        return results, dropped, latencies

    async def _search_one(self, source: RecallSource, query: RetrievalQuery) -> RetrievalResult:
        """单源检索，带 per-source SLA 超时熔断。"""
        start = time.perf_counter()
        try:
            res = await asyncio.wait_for(source.search(query), timeout=source.latency_budget_ms / 1000.0)
            res.latency_ms = (time.perf_counter() - start) * 1000
            return res
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            return RetrievalResult(
                source_name=source.name,
                error="timeout",
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # noqa: BLE001
            return RetrievalResult(
                source_name=source.name,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

    @staticmethod
    def _collect_evidence(results: list[RetrievalResult]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for res in results:
            evidence.extend(res.evidence)
        return evidence

    @staticmethod
    def _append_new(products: list[dict[str, Any]], results: list[RetrievalResult]) -> list[dict[str, Any]]:
        """把 fallback 结果里的新商品追加到现有列表尾部（按 product_id 去重）。"""
        existing = {str(p.get("product_id", "")) for p in products}
        for res in results:
            for product in res.products:
                pid = str(product.get("product_id", ""))
                if pid and pid not in existing:
                    products.append(product)
                    existing.add(pid)
        return products
