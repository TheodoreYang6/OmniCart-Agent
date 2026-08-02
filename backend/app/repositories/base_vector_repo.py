"""向量仓库抽象基类 — Qdrant / Stub 实现均继承此类。"""

from abc import ABC, abstractmethod


class BaseVectorRepository(ABC):

    @abstractmethod
    def search_similar(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        """向量相似搜索，返回 [{product_id, score, payload}, ...]."""
        ...

    @abstractmethod
    def store_embeddings(self, texts: list[str], embeddings: list[list[float]]):
        """批量存储文本和对应的嵌入向量。"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """检查向量库是否可用。"""
        ...

    # ---- V5 统一 chunk 单集合检索（默认空实现，Qdrant 覆写）----

    def search_chunks(
        self,
        query_vector: list[float],
        top_k: int = 30,
        filters: dict | None = None,
        chunk_types: list[str] | None = None,
        sparse: tuple[list[int], list[float]] | None = None,
    ) -> list[dict]:
        """块级向量检索（服务端 payload 过滤）。

        filters: {category, sub_category, price_max, price_min, rating_min}
        sparse: BM25 稀疏向量 (indices, values)；不为空时后端可做 dense+sparse 混合检索
        返回 [{product_id, chunk_id, chunk_type, category, sub_category, price, score, payload}]
        """
        return []

    def ensure_payload_indexes(self) -> None:
        """确保过滤字段建有 payload 索引（幂等）。默认 no-op。"""
        return None
