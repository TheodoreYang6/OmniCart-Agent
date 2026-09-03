from app.schemas.product import FaqItem, Product, RagKnowledge, ReviewItem
from app.schemas.product_chunk_v9 import build_chunks_v9, split_semantic_text
from app.services.candidate_llm_filter import deterministic_filter, validate_filter_result


def _product() -> Product:
    return Product(
        product_id="p-1",
        title="示例蓝牙耳机",
        brand="欧米",
        category="数码电子",
        sub_category="真无线耳机",
        base_price=399,
        image_path="2_数码电子/images/p-1.jpg",
        skus=[],
        rag_knowledge=RagKnowledge(
            marketing_description="舒适佩戴。" * 100,
            official_faq=[FaqItem(question="续航多久？", answer="充电盒可提供长续航。" * 60)],
            user_reviews=[
                ReviewItem(nickname="a", rating=5, content="佩戴舒适，通勤很好用。"),
                ReviewItem(nickname="b", rating=2, content="降噪效果一般。"),
            ],
        ),
    )


def test_v9_split_preserves_overlap_and_boundaries():
    chunks = split_semantic_text("第一段。" * 120)
    assert len(chunks) > 1
    assert all(len(chunk) <= 321 for chunk in chunks)
    assert chunks[0][-20:] in chunks[1]


def test_v9_builds_all_source_backed_chunk_types():
    chunks = build_chunks_v9(_product(), [{"fact_key": "spec.颜色", "value_text": "黑色", "source_text": "颜色: 黑色"}])
    types = {chunk.chunk_type for chunk in chunks}
    assert {"identity", "facts", "marketing", "faq", "review", "review_aspect"} <= types
    assert all(chunk.product_id == "p-1" and "[商品] 示例蓝牙耳机" in chunk.text for chunk in chunks)
    aspects = [chunk for chunk in chunks if chunk.chunk_type == "review_aspect"]
    assert aspects and all(chunk.source_refs for chunk in aspects)


def test_filter_rejects_out_of_scope_ids_and_budget():
    candidates = [
        {"product_id": "a", "price": 100, "matched_chunks": []},
        {"product_id": "b", "price": 500, "matched_chunks": []},
    ]
    result = validate_filter_result(
        {
            "primary": [
                {"product_id": "a", "reason": "ok"},
                {"product_id": "outside", "reason": "bad"},
                {"product_id": "b", "reason": "over"},
            ],
            "alternative": [],
            "conditional": [],
            "exclude": [],
        },
        candidates,
        {"budget_max": 300},
    )
    assert result is not None
    assert [x["product_id"] for x in result["primary"]] == ["a"]
    assert [x["product_id"] for x in result["exclude"]] == ["b"]


def test_filter_fallback_keeps_rerank_order():
    result = deterministic_filter(
        [
            {"product_id": "a", "price": 99, "matched_chunks": []},
            {"product_id": "b", "price": 199, "matched_chunks": []},
        ],
        {"budget_max": 300},
        "timeout",
    )
    assert [x["product_id"] for x in result["primary"]] == ["a", "b"]
    assert result["status"] == "fallback"


def test_explicit_missing_group_never_falls_back_to_irrelevant_cards():
    from app.retrieval.tool_chunk_retriever_v9 import ToolChunkRetrieverV9

    candidates = [{"product_id": "speaker"}, {"product_id": "scale"}]
    out = ToolChunkRetrieverV9._apply_filter(
        candidates,
        {
            "primary": [],
            "alternative": [],
            "conditional": [],
            "exclude": [],
            "missing_group": "缺少蓝牙耳机候选",
            "status": "model",
        },
        5,
    )
    assert out == []


async def test_tool_search_embeds_once_and_reuses_the_same_hit_snapshot():
    from app.retrieval.tool_chunk_retriever_v9 import ToolChunkRetrieverV9
    from app.schemas.workflow import Constraints, RetrievalPlan

    product = _product()
    hit_chunk = build_chunks_v9(product)[0]

    class Repo:
        def get_by_id(self, product_id):
            return product if product_id == product.product_id else None

    class Gateway:
        calls = 0

        async def embed(self, texts, *args, **kwargs):
            self.calls += 1
            return [[0.1, 0.2]]

    class Retriever(ToolChunkRetrieverV9):
        def _vector_dimension_matches(self, vector):
            return True

        def _query_chunks(self, vector, query, filters, hybrid):
            assert vector == [0.1, 0.2]
            return [
                {
                    "product_id": product.product_id,
                    "score": 0.9,
                    "chunk_type": "identity",
                    "payload": hit_chunk.to_qdrant_payload(),
                }
            ]

    gateway = Gateway()
    result = await Retriever(repo=Repo(), gateway=gateway)._search_once(
        "蓝牙耳机", RetrievalPlan(), Constraints(), "risk_check", 5, "test"
    )
    assert gateway.calls == 1
    assert result["chunk_hits"] == 1
    assert result["products"][0]["product_id"] == product.product_id
    assert result["products"][0]["image_urls"] == ["/api/products/p-1/image"]


def test_mock_embedding_honours_index_dimension():
    """Mock 必须遵守 embedding 协议，否则测试/降级环境会把 Qdrant 查询打空。"""
    from app.model_gateway.mock_model import MockEmbedding

    assert len(MockEmbedding().embed(["蓝牙耳机"], dimensions=1024)[0]) == 1024


def test_missing_local_vector_cache_falls_back_to_catalog_lexical_search(monkeypatch):
    """Fresh clones have no generated backend/data index but must still retrieve products."""
    from app.retrieval import tool_chunk_retriever_v9 as module

    product = _product()

    class Repo:
        def search_text(self, query, top_k=100):
            assert query == "蓝牙耳机"
            return [product]

    retriever = module.ToolChunkRetrieverV9(repo=Repo(), gateway=object(), filterer=object())
    monkeypatch.setattr(module, "USE_QDRANT", False)
    monkeypatch.setattr(retriever, "_local_hits", lambda vector, filters: [])

    hits = retriever._query_chunks([0.1, 0.2], "蓝牙耳机", {"category": "数码电子"}, False)

    assert [hit["product_id"] for hit in hits] == [product.product_id]
    assert hits[0]["chunk_type"] == "identity"


def test_router_alias_subcategory_is_not_used_as_exact_vector_filter():
    """“蓝牙耳机”不是库内“真无线耳机”时，不能把整组候选过滤为空。"""
    from app.retrieval.tool_chunk_retriever_v9 import ToolChunkRetrieverV9

    class Repo:
        def get_sub_categories(self, _category):
            return ["真无线耳机", "头戴式耳机"]

    retriever = ToolChunkRetrieverV9(repo=Repo())
    assert retriever._validated_filters({"category": "数码电子", "sub_category": "蓝牙耳机"})["sub_category"] is None
    assert (
        retriever._validated_filters({"category": "数码电子", "sub_category": "真无线耳机"})["sub_category"]
        == "真无线耳机"
    )
