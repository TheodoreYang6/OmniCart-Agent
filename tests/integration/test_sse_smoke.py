"""P3-1: SSE Smoke Test — 校验流式推荐事件顺序、字段完整性和端到端正确性。

Run with: pytest tests/integration/test_sse_smoke.py -v
Requires backend running on 127.0.0.1:8006
"""

import json
import httpx
import pytest

BASE = "http://127.0.0.1:8006"

# Required fields in SSE result event (audit report §12)
RESULT_REQUIRED_FIELDS = [
    "session_id", "conversation_id", "answer",
    "products", "decision_results", "evidence_list", "trace_steps",
    "harness_report", "used_memories", "blocked_memories", "memory_trace",
]

# 决策结果只下发用户可理解的结论；内部数值评分仅留在服务端诊断账本。
DECISION_FIELDS = [
    "product_id", "recommendation_level", "match_label", "evidence_label",
    "why_it_fits", "caution",
]

# Product fields each product should have
PRODUCT_FIELDS = [
    "product_id", "title", "brand", "category", "price",
]


@pytest.fixture
def async_client():
    return httpx.AsyncClient(timeout=60.0, trust_env=False)


@pytest.mark.asyncio
async def test_sse_event_order(async_client):
    """SSE 事件顺序：阶段 → 卡片 → 真实 token → result → done。"""
    events = []
    async with async_client.stream(
        "POST", f"{BASE}/api/recommend/stream",
        json={
            "session_id": "sse_smoke_test_001",
            "user_id": "test_user",
            "message": "推荐通勤充电宝",
        },
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data = line[5:].strip()
                # Parse event type from previous line (SSE convention)
                event_type = "unknown"
                for e in events[::-1]:
                    if e[0] == "event":
                        event_type = e[1]
                        break
                events.append((event_type, data))
            elif line.startswith("event:"):
                events.append(("event", line[6:].strip()))

    # Verify event sequence
    event_types = [e[0] for e in events if e[0] != "event"]
    assert "token" in event_types, "Missing token events"
    assert "result" in event_types, "Missing result event"
    assert "done" in event_types, "Missing done event"

    # token before result before done
    token_indices = [i for i, t in enumerate(event_types) if t == "token"]
    result_idx = event_types.index("result")
    done_idx = event_types.index("done")
    assert token_indices[0] < result_idx, "token must appear before result"
    assert result_idx < done_idx, "result must appear before done"


@pytest.mark.asyncio
async def test_sse_result_fields(async_client):
    """SSE result 事件包含所有必需字段。"""
    result_data = await _get_sse_result(async_client, "推荐通勤充电宝")
    missing = [f for f in RESULT_REQUIRED_FIELDS if f not in result_data]
    assert not missing, f"Missing fields in SSE result: {missing}"


@pytest.mark.asyncio
async def test_sse_result_has_products(async_client):
    """SSE result 返回商品列表且字段完整。"""
    result_data = await _get_sse_result(async_client, "推荐通勤充电宝")
    products = result_data.get("products", [])
    assert len(products) > 0, "SSE result should return at least 1 product"

    for p in products:
        for field in PRODUCT_FIELDS:
            assert field in p, f"Product missing field: {field}"


@pytest.mark.asyncio
async def test_sse_result_has_decisions(async_client):
    """SSE result 的 decision_results 仅包含用户可理解的卡片结论。"""
    result_data = await _get_sse_result(async_client, "推荐通勤充电宝")
    decisions = result_data.get("decision_results", [])
    assert len(decisions) > 0, "SSE result should have decision results"

    for d in decisions:
        for field in DECISION_FIELDS:
            assert field in d, f"Decision missing field: {field}"
        assert "final_score" not in d
        assert "display_score" not in d


@pytest.mark.asyncio
async def test_sse_guest_does_not_persist_conversation(async_client):
    """匿名推荐是一次性的，伪造 body user_id 也不能创建历史会话。"""
    result_data = await _get_sse_result(
        async_client, "出差用的充电宝",
        conversation_id=""
    )
    conv_id = result_data.get("conversation_id", "")
    assert conv_id == ""


@pytest.mark.asyncio
async def test_sse_memory_trace_fields(async_client):
    """memory_trace 至少有基本结构 (P0-1 已写回 lastResponse)。"""
    result_data = await _get_sse_result(async_client, "推荐一款适合通勤的耳机")
    memory_trace = result_data.get("memory_trace", {})
    assert isinstance(memory_trace, dict), "memory_trace must be a dict"


async def _get_sse_result(
    async_client: httpx.AsyncClient, message: str,
    session_id: str = "", conversation_id: str = "",
) -> dict:
    """Helper: 发送 SSE 请求并收集 result 事件的 JSON 数据。"""
    import uuid
    sid = session_id or f"smoke_{uuid.uuid4().hex[:8]}"

    result_str = ""
    async with async_client.stream(
        "POST", f"{BASE}/api/recommend/stream",
        json={
            "session_id": sid,
            "user_id": "test_smoke_user",
            "conversation_id": conversation_id,
            "message": message,
        },
    ) as response:
        response.raise_for_status()
        current_event = ""
        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:") and current_event == "result":
                result_str = line[5:].strip()
                break

    assert result_str, f"No SSE result received for query: {message[:30]}"
    return json.loads(result_str)
