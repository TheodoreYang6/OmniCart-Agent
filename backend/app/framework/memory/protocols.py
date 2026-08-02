"""Memory 框架层核心契约（借鉴 amap ``libs/memory_bank``）。

定义记忆项、召回请求/结果，以及三组可插拔 Protocol：
- :class:`MemoryProvider`：一类记忆源（短期/长期偏好/会话），MemoryBank 并行分发的单元。
- :class:`RetrievalPath`：单个 Provider 内部的一路召回（Vector/BM25/Tag），供 RecallEngine 编排。
- :class:`FusionStrategy` / :class:`RerankStrategy`：多路融合与重排策略。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class MemoryItem:
    """统一记忆项。

    Attributes:
        memory_id: 唯一标识（去重键）。
        text: 可读文本（注入 prompt 用）。
        score: 相关性/融合分。
        embedding: 可选向量（供 MMR 多样性重排）。
        memory_type: preference / short_term / conversation。
        extra: 业务字段（如 category / brands / avoid_tags / confidence / timestamp）。
    """

    memory_id: str
    text: str = ""
    score: float = 0.0
    embedding: list[float] = field(default_factory=list)
    memory_type: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecallRequest:
    """记忆召回请求。"""

    user_id: str
    query: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    top_n: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecallResult:
    """单个 Provider 的召回结果。"""

    provider_name: str
    items: list[MemoryItem] = field(default_factory=list)
    error: str | None = None
    latency_ms: float = 0.0


class MemoryProvider(ABC):
    """记忆 Provider 抽象基类 —— MemoryBank 并行分发的单元。"""

    name: str = ""
    priority: int = 100

    def should_activate(self, request: MemoryRecallRequest) -> bool:
        return True

    @abstractmethod
    async def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult: ...


@runtime_checkable
class RetrievalPath(Protocol):
    """单路召回协议（Provider 内部使用，供 RecallEngine 并行编排）。"""

    name: str

    async def retrieve(self, request: MemoryRecallRequest) -> list[MemoryItem]: ...


@runtime_checkable
class FusionStrategy(Protocol):
    """多路融合策略协议（N 路 → 1 路有序列表）。"""

    def fuse(self, path_results: dict[str, list[MemoryItem]]) -> list[MemoryItem]: ...


@runtime_checkable
class RerankStrategy(Protocol):
    """重排策略协议（融合后 → 重排）。"""

    def rerank(self, items: list[MemoryItem]) -> list[MemoryItem]: ...


@runtime_checkable
class QueryRewriter(Protocol):
    """记忆查询改写协议。"""

    async def rewrite(self, request: MemoryRecallRequest) -> str: ...
