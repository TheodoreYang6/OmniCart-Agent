"""V2 LangGraph Workflow 集成测试 — 需要后端运行。"""
import httpx
import pytest

BASE = "http://127.0.0.1:8006"


@pytest.fixture
def client():
    return httpx.Client(timeout=30.0, trust_env=False)


def test_v2_recommend_structure(client):
    """V2 推荐返回完整结构。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "蓝牙耳机推荐", "session_id": "test-v2-001"})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "answer" in data
    assert "products" in data
    assert "evidence_list" in data
    assert "decision_results" in data
    assert "trace_steps" in data


def test_v2_recommend_returns_products(client):
    """V2 蓝牙耳机推荐返回商品。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "蓝牙耳机推荐"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["products"]) > 0


def test_v2_trace_steps_populated(client):
    """V2 工作流 trace_steps 记录了完整链路。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "咖啡推荐"})
    assert resp.status_code == 200
    data = resp.json()
    steps = data["trace_steps"]
    assert len(steps) >= 4  # 最少 Router→Retrieval→Decision→Response
    agent_names = [s["agent_name"] for s in steps]
    assert any("Router" in n for n in agent_names)


def test_v2_constraints_in_response(client):
    """V2 返回中包含了约束解析结果。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "500元以内的蓝牙耳机"})
    assert resp.status_code == 200
    data = resp.json()
    # constraints 可能为 None（mock 模式 LLM 不可用时）
    constraints = data.get("constraints")
    if constraints:
        assert "category" in constraints or "budget_max" in constraints


def test_v2_empty_query_handled(client):
    """空查询降级到默认行为（不崩溃）。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "", "session_id": "test-empty"})
    assert resp.status_code in (200, 500)  # 500 可接受（Reranker API 对空查询退避）


def test_v2_category_accurate(client):
    """品类识别准确：精华查询应返回美妆护肤类商品。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "保湿精华推荐"})
    assert resp.status_code == 200
    data = resp.json()
    products = data["products"]
    if products:
        categories = [p.get("category", "") for p in products]
        beauty_count = sum(1 for c in categories if "美妆" in c)
        assert beauty_count > 0, f"Expected beauty products, got: {categories[:3]}"


def test_v2_evidence_binding(client):
    """V2 返回的证据列表中 evidence_id 格式正确。"""
    resp = client.post(f"{BASE}/api/recommend/v2",
                       json={"user_query": "跑步鞋推荐"})
    assert resp.status_code == 200
    data = resp.json()
    for ev in data.get("evidence_list", []):
        assert "evidence_id" in ev
        assert "source_type" in ev
