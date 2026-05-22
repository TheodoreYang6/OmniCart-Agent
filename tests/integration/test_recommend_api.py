"""Integration test for /api/recommend.

Run with: pytest tests/integration/test_recommend_api.py -v
Requires backend running on 127.0.0.1:8006
"""

import httpx
import pytest

BASE = "http://127.0.0.1:8006"


@pytest.fixture
def client():
    return httpx.Client(timeout=30.0, trust_env=False)


def test_health(client):
    resp = client.get(f"{BASE}/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_recommend_returns_structure(client):
    resp = client.post(
        f"{BASE}/api/recommend",
        json={"user_query": "出差用的20000mAh充电宝"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "answer" in data
    assert "products" in data
    assert "evidence_list" in data
    assert "decision_results" in data
    assert "trace_steps" in data


def test_recommend_with_budget(client):
    resp = client.post(
        f"{BASE}/api/recommend",
        json={"user_query": "100元以内的充电宝"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Products returned should all be under budget
    for p in data["products"]:
        assert p["price"] <= 100, f"Expected price <= 100, got {p['price']}"


def test_recommend_no_results(client):
    resp = client.post(
        f"{BASE}/api/recommend",
        # V0 price parser supports specific values; "1元" filters all
        json={"user_query": "50元以内的充电宝"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["products"]) == 0
    assert len(data["answer"]) > 0  # should have a fallback message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
