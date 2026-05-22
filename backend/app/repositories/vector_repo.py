"""向量仓库 — 工厂重导出。

根据 USE_QDRANT 配置自动选择：
- True  → QdrantVectorRepository（语义向量搜索）
- False → StubVectorRepository（降级，返回空结果）

保持向后兼容：`from app.repositories.vector_repo import VectorRepository` 仍然可用。
"""

from app.core.config import USE_QDRANT
from app.core.qdrant_client import get_qdrant
from app.repositories.base_vector_repo import BaseVectorRepository
from app.repositories.qdrant_vector_repo import QdrantVectorRepository
from app.repositories.stub_vector_repo import StubVectorRepository

if USE_QDRANT:
    _client = get_qdrant()
    if _client is not None:
        VectorRepository = QdrantVectorRepository(_client)  # type: ignore[assignment]
    else:
        VectorRepository = StubVectorRepository()  # type: ignore[assignment]
else:
    VectorRepository = StubVectorRepository()  # type: ignore[assignment]


def get_vector_repo() -> BaseVectorRepository:
    """返回当前活动的向量仓库实例。"""
    if USE_QDRANT:
        client = get_qdrant()
        if client is not None:
            return QdrantVectorRepository(client)
    return StubVectorRepository()
