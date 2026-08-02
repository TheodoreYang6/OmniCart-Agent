"""V6 分块与过滤单测 —— Contextual Prefix / FAQ 400 / 规格入向量 / 去昵称 / 口碑 payload / brand 过滤。"""

from app.schemas.product_chunk import ProductChunk, build_chunks, chunk_point_id
from app.schemas.product import Product, RagKnowledge, FaqItem, ReviewItem, Sku


def _product(faq_answer_len: int = 300) -> Product:
    return Product(
        product_id="p_test_001",
        title="测试牌超长效保温杯不锈钢真空316L食品级大容量便携水杯500ml",
        brand="测试牌",
        category="家居用品",
        sub_category="保温杯",
        base_price=99.0,
        image_path="x.jpg",
        skus=[
            Sku(sku_id="s1", properties={"容量": "500ml", "颜色": "曜石黑"}, price=99.0),
            Sku(sku_id="s2", properties={"容量": "750ml", "颜色": "云朵白"}, price=129.0),
        ],
        rag_knowledge=RagKnowledge(
            marketing_description="测试牌保温杯采用316L不锈钢内胆" + "工艺" * 100,
            official_faq=[FaqItem(question="保温能保多久？", answer="实测数据" * (faq_answer_len // 4))],
            user_reviews=[
                ReviewItem(nickname="李小米", rating=5, content="用了三个月保温效果依旧" * 5),
                ReviewItem(nickname="王梓涵", rating=2, content="杯盖漏水有点失望" * 5),
            ],
        ),
    )


def test_chunks_have_contextual_prefix():
    p = _product()
    chunks = build_chunks(p)
    by_type = {c.chunk_type: c for c in chunks}
    prefix = f"[{p.brand} {p.sub_category}] "
    assert by_type["mkt"].text.startswith(prefix)
    assert by_type["rev"].text.startswith(prefix)
    # faq 不加前缀：问句自带商品指向，消融实验无前缀 hit@1 0.969 vs 加前缀 0.891
    assert by_type["faq"].text.startswith("Q: ")
    # summary 本身含全量信息，不加前缀
    assert by_type["summary"].text.startswith("[产品]")


def test_faq_answer_truncated_at_400():
    chunks = build_chunks(_product(faq_answer_len=600))
    faq = next(c for c in chunks if c.chunk_type == "faq")
    answer_part = faq.text.split(" A: ", 1)[1]
    assert len(answer_part) == 400  # 600 字答案截 400（旧版 200 丢参数尾部）
    assert faq.text.startswith("Q: ")


def test_summary_contains_sku_spec():
    chunks = build_chunks(_product())
    summary = next(c for c in chunks if c.chunk_type == "summary")
    assert "[规格]" in summary.text
    assert "容量:500ml/750ml" in summary.text
    assert "颜色:曜石黑/云朵白" in summary.text


def test_rev_chunk_has_no_nickname_in_text():
    chunks = build_chunks(_product())
    rev = next(c for c in chunks if c.chunk_type == "rev")
    assert "李小米" not in rev.text          # 昵称退出 embedding 文本（噪音）
    assert "评分5/5:" in rev.text
    assert rev.review_nickname == "李小米"   # payload 保留供展示


def test_rating_aggregates_in_payload():
    chunks = build_chunks(_product())
    for c in chunks:
        payload = c.to_qdrant_payload()
        assert payload["avg_rating"] == 3.5   # (5+2)/2
        assert payload["review_count"] == 2
        assert payload["negative_count"] == 1
    # 双向映射一致
    rt = ProductChunk.from_qdrant_payload(chunks[0].to_qdrant_payload())
    assert rt.avg_rating == 3.5 and rt.review_count == 2


def test_chunk_point_id_stable():
    assert chunk_point_id("a|b|0") == chunk_point_id("a|b|0")
    assert chunk_point_id("a|b|0") != chunk_point_id("a|b|1")


def test_build_filter_brand_and_rating():
    from app.repositories.qdrant_vector_repo import QdrantVectorRepository

    f = QdrantVectorRepository._build_filter(
        {"brand": ["膳魔师", "虎牌"], "rating_min": 4.0, "category": "家居用品"},
        chunk_types=["summary"])
    keys = [c.key for c in f.must]
    assert set(keys) == {"brand", "avg_rating", "category", "chunk_type"}
    # 单品牌字符串形式
    f2 = QdrantVectorRepository._build_filter({"brand": "膳魔师"}, None)
    assert [c.key for c in f2.must] == ["brand"]
