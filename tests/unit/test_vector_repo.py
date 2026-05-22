"""向量仓库单元测试。"""

import pytest

from app.repositories.stub_vector_repo import StubVectorRepository


class TestStubVectorRepository:
    """Stub 实现应优雅降级，不抛异常。"""

    def test_search_returns_empty_list(self):
        repo = StubVectorRepository()
        result = repo.search_similar([0.1] * 1024, top_k=10)
        assert result == []

    def test_store_embeddings_is_noop(self):
        repo = StubVectorRepository()
        repo.store_embeddings(["test"], [[0.1] * 1024])
        # 不抛异常即为通过

    def test_health_check_returns_false(self):
        repo = StubVectorRepository()
        assert repo.health_check() is False
