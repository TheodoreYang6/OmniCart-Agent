import pytest
from app.repositories.product_repo import ProductRepository
from app.retrieval.text_retriever import TextRetriever


@pytest.mark.asyncio
async def test_retriever_returns_results():
    repo = ProductRepository()
    retriever = TextRetriever(repo)
    results = await retriever.search("蓝牙耳机", top_k=5)
    assert len(results) > 0
    assert len(results) <= 5


@pytest.mark.asyncio
async def test_retriever_result_has_required_fields():
    repo = ProductRepository()
    retriever = TextRetriever(repo)
    results = await retriever.search("蓝牙耳机", top_k=3)
    for r in results:
        assert "product_id" in r
        assert "title" in r
        assert "price" in r
        assert "score" in r
        assert "evidence_ids" in r
        assert "image_urls" in r


@pytest.mark.asyncio
async def test_retriever_price_filter():
    repo = ProductRepository()
    retriever = TextRetriever(repo)
    results = await retriever.search("蓝牙耳机", top_k=20, price_max=200)
    for r in results:
        assert r["price"] <= 200


@pytest.mark.asyncio
async def test_retriever_category_filter():
    repo = ProductRepository()
    retriever = TextRetriever(repo)
    results = await retriever.search("保湿精华", top_k=10, category="美妆护肤")
    for r in results:
        assert r["category"] == "美妆护肤"


@pytest.mark.asyncio
async def test_retriever_empty_on_mismatch():
    repo = ProductRepository()
    retriever = TextRetriever(repo)
    results = await retriever.search("蓝牙耳机", top_k=20, price_max=1)
    assert results == []
