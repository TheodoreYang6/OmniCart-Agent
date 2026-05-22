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
