"""RAG 框架层核心数据模型（借鉴 amap ``libs/knowledge_base/types.py``）。

与 amap 的差异：amap 是**文档中心**（``Document``），OmniCart 是**商品 + 证据中心**
——检索产出 ``products``（商品 dict）与 ``evidence``（证据 dict），下游 Decision /
Guard / Android 直接消费这两个结构。因此本模块把 amap 的 Document 模型适配为
商品/证据双载荷，保证重构后主链路契约字节级不变。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalQuery:
    """一次检索的输入（由 RetrievalAgent 从 WorkflowState 构建）。

    Attributes:
        query: 用户原始查询。
        rewritten_query: 改写后的检索串（由 QueryRewriter 阶段填充；空则回退 query）。
        category / sub_category: 品类硬过滤。
        budget_max / budget_min: 价格硬过滤。
        scenario: 场景。
        must_tags / spec_keywords: 供 rewriter 拼接检索串。
        exclude_tags: 避雷标签（供 recall 源感知；硬过滤仍在 graph 层做）。
        top_k: 返回商品数上限。
        min_results: 少于该数触发 fallback 阶段（对齐现 retrieval_agent 的 `<3` 逻辑）。
        seed_products: 已召回商品，供 enrich 阶段（review/policy）二次挖掘证据。
        context: 会话上下文（供 LLM 改写指代消解）。
        metadata: 扩展容器。
    """

    query: str
    rewritten_query: str = ""
    category: str | None = None
    sub_category: str | None = None
    budget_max: float | None = None
    budget_min: float | None = None
    scenario: str | None = None
    must_tags: list[str] = field(default_factory=list)
    spec_keywords: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    top_k: int = 10
    min_results: int = 3
    rating_min: float | None = None  # 口碑下限（avg_rating 服务端过滤，spec omni-harness D3）
    chunk_focus: str | None = None  # 聚焦块类型 rev/faq（原子检索）
    seed_products: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_query(self) -> str:
        """实际用于向量检索的查询串：优先改写结果。"""
        return self.rewritten_query or self.query


@dataclass
class RetrievalResult:
    """单个召回源的产出。

    products 与 evidence 均为下游可直接消费的 dict 列表，结构与现
    ``retrieval_agent`` 各通道保持一致（product_id/title/... 与
    evidence_id/source_type/...）。
    """

    source_name: str
    products: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class RetrievalBundle:
    """编排器融合后的最终检索结果包。"""

    products: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    dropped_sources: list[str] = field(default_factory=list)
    per_source_latency_ms: dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
