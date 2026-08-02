"""商品融合策略（借鉴 amap ``libs/memory_bank/recall/fusion.py`` 的 RRF 思想）。

职责：把多个召回源产出的商品列表合并为单一有序列表（去重 + 排序）。证据（evidence）
的合并由编排器直接做并集，不在此处。

内置：
- ``SequentialFusion``：按源 priority 顺序拼接 + 按 product_id 去重（保留首次出现顺序）。
  这是默认策略，复现现 retrieval_agent「text 结果在前、supplementary 追加在后」的行为。
- ``RRFFusion``：Reciprocal Rank Fusion，各源内按 score 排名后用 ``1/(k+rank)`` 融合，
  适合多路语义/关键词召回需要平衡排名的场景（可选启用）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.framework.retrieval.types import RetrievalResult


@runtime_checkable
class RetrievalFusion(Protocol):
    """商品融合策略协议。"""

    def fuse(self, results: list[RetrievalResult]) -> list[dict[str, Any]]:
        """把多源结果融合为单一有序商品列表。"""
        ...


def _pid(product: dict[str, Any]) -> str:
    return str(product.get("product_id", ""))


class SequentialFusion:
    """顺序拼接 + 去重（默认策略）。

    编排器已按 source.priority 升序传入 results，故此处只需按序遍历、按 product_id
    去重、保留首次出现顺序。刻意不重排 —— 排名交给下游 Reranker 节点（graph 层），
    以保证与现有行为字节级一致。
    """

    def fuse(self, results: list[RetrievalResult]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for result in results:
            for product in result.products:
                pid = _pid(product)
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                merged.append(product)
        return merged


class RRFFusion:
    """Reciprocal Rank Fusion（可选策略）。

    公式：``score(p) = Σ_source 1/(k + rank_source(p))``；各源内按商品 ``score`` 字段
    降序得到 rank。融合分写回商品 dict 的 ``rrf_score`` 字段，最终按 rrf_score 降序。

    Args:
        k: RRF 平滑常数，默认 60（业界惯例）。
    """

    def __init__(self, *, k: int = 60) -> None:
        self._k = k

    def fuse(self, results: list[RetrievalResult]) -> list[dict[str, Any]]:
        pool: dict[str, dict[str, Any]] = {}
        rrf: dict[str, float] = {}

        for result in results:
            ranked = sorted(
                result.products,
                key=lambda p: float(p.get("score", 0.0) or 0.0),
                reverse=True,
            )
            for rank, product in enumerate(ranked, start=1):
                pid = _pid(product)
                if not pid:
                    continue
                if pid not in pool:
                    pool[pid] = product
                rrf[pid] = rrf.get(pid, 0.0) + 1.0 / (self._k + rank)

        ordered = sorted(pool.keys(), key=lambda pid: rrf[pid], reverse=True)
        out: list[dict[str, Any]] = []
        for pid in ordered:
            product = dict(pool[pid])
            product["rrf_score"] = round(rrf[pid], 6)
            out.append(product)
        return out
