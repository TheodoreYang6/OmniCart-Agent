"""混合检索单元测试 — 验证 jieba + Qdrant RRF 融合 + 降级行为。"""

import pytest

from app.repositories.stub_vector_repo import StubVectorRepository


class TestHybridSearch:
    """测试 hybrid_search 在各种向量仓库状态下的行为。"""

    @pytest.mark.asyncio
    async def test_hybrid_with_stub_falls_back_to_text(self, text_retriever):
        """Stub 向量仓库 → hybrid_search 应降级为纯关键词搜索。"""
        results = await text_retriever.hybrid_search("蓝牙耳机", top_k=5)
        assert len(results) > 0, "降级后应返回关键词搜索结果"
        for r in results:
            assert "product_id" in r
            assert "title" in r
            assert "score" in r

    @pytest.mark.asyncio
    async def test_hybrid_returns_evidence_ids(self, text_retriever):
        """hybrid_search 结果应包含 evidence_ids。"""
        results = await text_retriever.hybrid_search("精华", top_k=3)
        for r in results:
            assert "evidence_ids" in r
            assert len(r["evidence_ids"]) > 0

    @pytest.mark.asyncio
    async def test_hybrid_respects_top_k(self, text_retriever):
        """结果数量不应超过 top_k。"""
        results = await text_retriever.hybrid_search("咖啡", top_k=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_hybrid_empty_query_returns_results(self, text_retriever):
        """空查询不应崩溃。"""
        results = await text_retriever.hybrid_search("", top_k=5)
        assert isinstance(results, list)

    def test_rrf_fusion_raises_no_error(self, text_retriever):
        """RRF 融合不应抛出异常。"""
        list_a = [{"product_id": "a", "title": "A", "score": 1.0, "evidence_ids": ["e1"]}]
        list_b = [{"product_id": "b", "title": "B", "score": 0.9, "evidence_ids": ["e2"]}]
        merged = text_retriever._rrf_fusion(list_a, list_b)
        assert len(merged) == 2

    @pytest.mark.asyncio
    async def test_hybrid_search_format_matches_search(self, text_retriever):
        """hybrid_search 格式应与 search() 一致。"""
        text_results = await text_retriever.search("防晒", top_k=3)
        hybrid_results = await text_retriever.hybrid_search("防晒", top_k=3)

        # 结果应包含相同字段
        if text_results and hybrid_results:
            for key in text_results[0]:
                assert key in hybrid_results[0], f"hybrid 结果缺少字段: {key}"
