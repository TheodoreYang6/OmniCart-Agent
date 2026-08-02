"""精排协议（融合之后、决策之前的独立环节）。

框架层只定义协议；具体实现（LLM 精排 + 校准 + 视觉置顶钩子）见
``app.providers.recall.rerank_fusion.RerankFusion``。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Reranker(Protocol):
    """精排器协议：对商品列表重排并写回分数。"""

    async def rerank(
        self,
        *,
        query: str,
        products: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        visual_matched_pids: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...
