"""Stub 向量仓库 — 优雅降级实现。

当 Qdrant 不可用或未配置时使用，所有方法返回空结果而不抛异常。
"""

from app.repositories.base_vector_repo import BaseVectorRepository


class StubVectorRepository(BaseVectorRepository):
    """无 Qdrant 时的降级实现 — 静默返回空结果。"""

    def search_similar(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        return []

    def store_embeddings(self, texts: list[str], embeddings: list[list[float]]):
        pass

    def health_check(self) -> bool:
        return False
