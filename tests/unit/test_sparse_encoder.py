"""BM25 稀疏编码器单测（spec: 混合检索与四bug根治 §1.1）。"""

from app.retrieval import sparse_encoder as se


def test_tokenize_keeps_model_numbers():
    """型号必须整体保留 —— 电商强信号，切碎则失去精确召回能力。"""
    toks = se.tokenize("膳魔师JBC-351儿童保温杯350ml")
    assert "jbc-351" in toks, toks
    assert "350ml" in toks or "350" in "".join(toks), toks
    assert any("保温" in t or t == "杯" for t in toks), toks


def test_tokenize_filters_stopwords():
    toks = se.tokenize("我想买一个适合敏感肌的面膜")
    assert "面膜" in toks
    for stop in ("我", "的", "想", "一个", "适合"):
        assert stop not in toks, f"停用词未过滤: {stop}"


def test_tokenize_english_brand():
    toks = se.tokenize("SK-II护肤精华露230ml")
    assert "sk-ii" in toks, toks


def test_encode_document_and_query_share_dims():
    """同一 token 在文档侧与查询侧必须落到同一维度（否则点积恒为 0）。"""
    stats = se.build_corpus_stats(["面膜补水保湿", "面霜滋润", "精华修护"])
    d_idx, d_val = se.encode_document("面膜补水保湿", stats)
    q_idx, q_val = se.encode_query("面膜", stats)
    assert d_idx and q_idx
    assert set(q_idx) & set(d_idx), "查询与文档无公共维度"
    assert all(v > 0 for v in d_val + q_val)


def test_bm25_ranks_exact_category_higher():
    """核心诉求：query『面膜』对面膜文档的 BM25 分必须高于面霜文档。"""
    corpus = [
        "面膜补水保湿贴片式",          # 目标
        "面霜滋润修护干皮适用",        # 语义邻近但品类不同
        "精华液抗氧化淡纹",
    ]
    stats = se.build_corpus_stats(corpus)
    q_idx, q_val = se.encode_query("面膜", stats)
    qmap = dict(zip(q_idx, q_val, strict=True))

    def score(doc: str) -> float:
        idx, val = se.encode_document(doc, stats)
        return sum(qmap.get(i, 0.0) * v for i, v in zip(idx, val, strict=True))

    s_mask, s_cream = score(corpus[0]), score(corpus[1])
    assert s_mask > s_cream, f"面膜({s_mask}) 未高于面霜({s_cream})"
    assert s_cream == 0.0 or s_mask / max(s_cream, 1e-9) > 1.5


def test_stats_missing_degrades_not_raises():
    """统计文件缺失时降级而非抛异常（降级链原则）。"""
    se.reset_stats_cache()
    st = se.load_stats(path=se.Path("/tmp/__no_such_bm25_stats__.json"))
    assert st.n_docs >= 1 and st.avgdl > 0
    idx, val = se.encode_query("面膜", st)
    assert idx == [] or all(v >= 0 for v in val)  # idf 可能全 0，但不得崩
    se.reset_stats_cache()


def test_empty_text_returns_empty():
    assert se.encode_document("") == ([], [])
    assert se.encode_query("   ") == ([], [])
