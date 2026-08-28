from app.observability.rag_logger import RagTrace


def test_v2_trace_records_verdict_not_deprecated_display_score():
    trace = RagTrace(session_id="s1", query="通勤降噪耳机")
    trace.set_embedding(
        query_vec=[],
        candidates=[{"product_id": "p1", "title": "耳机", "price": 299, "retrieval_source": "v9_chunk"}],
        latency_ms=12,
        retrieval_mode="v9",
    )
    trace.set_final(
        [{"product_id": "p1", "title": "耳机", "price": 299}],
        [{"product_id": "p1", "recommendation_level": "strong_recommend", "filter_verdict": "primary"}],
    )

    row = trace.trace["final_top5"][0]
    assert trace.trace["schema_version"] == "rag_trace_v2"
    assert trace.trace["retrieval_mode"] == "v9"
    assert row["filter_verdict"] == "primary"
    assert "display_score" not in row
