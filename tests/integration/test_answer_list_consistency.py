"""§5.2 验收：答文与列表强一致 + 深度购物动作权限（spec 混合检索与四bug根治）。

这两项是用户直报 bug 的验收口：
- bug#3 回答与商品列表不一致 → result.products 前 N 必须是回答引用集（同序）
- bug#4 深度思考下纯购物动作被错误交给自由 Loop → 必须直接走受控交易路由
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _last_result(raw: str) -> dict:
    """从 SSE 流中取最后一个 result 帧。"""
    out = {}
    for block in raw.split("\n\n"):
        if "event: result" in block:
            for line in block.splitlines():
                if line.startswith("data: "):
                    out = json.loads(line[6:])
    return out


@pytest.mark.integration
def test_guest_stream_does_not_trust_body_user_id_or_create_history():
    """匿名 SSE 可推荐，但请求体伪造 user_id 不会获得持久会话。"""
    client = TestClient(app)
    with client.stream("POST", "/api/recommend/stream", json={
        "user_id": "pretend_to_be_a_real_user", "conversation_id": "forged-conversation",
        "message": "推荐一个保温杯",
    }) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    result = _last_result(raw)
    assert result.get("conversation_id", "") == ""
    assert "event: stage" in raw
    assert "event: recommendations" in raw or not (result.get("products") or [])


@pytest.mark.integration
def test_recommendation_sections_are_bounded_and_answer_uses_primary_products():
    """新协议：首选≤3、备选≤6、互不重复，答文只应引用首选。"""
    client = TestClient(app)
    with client.stream("POST", "/api/recommend/stream", json={
        "user_id": "it_cited", "message": "推荐面膜",
    }) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    d = _last_result(raw)
    primary = d.get("primary_products") or []
    alternatives = d.get("alternative_products") or []
    products = d.get("products") or []
    if not products:
        pytest.skip("检索无结果（依赖向量库），跳过一致性断言")

    assert len(primary) <= 3
    assert len(alternatives) <= 6
    primary_ids = {p.get("product_id") for p in primary}
    alternative_ids = {p.get("product_id") for p in alternatives}
    assert primary_ids.isdisjoint(alternative_ids)
    assert products == primary + alternatives

    answer = d.get("answer") or ""
    assert answer, "应有回答"
    # 兑底/闲聊模板（测试环境 LLM 不可用时会走到）不参与引用校验——
    # 上面的置顶/beyond_answer 结构契约才是本测要锁的东西
    _FALLBACKS = ("没太看懂", "抑或欧米更擅长", "抱歉，没有找到")
    if any(f in answer for f in _FALLBACKS):
        pytest.skip(f"回答为兑底模板（LLM 不可用），已验结构契约: {answer[:24]}")
    # 回答至少引用一款首选，且不能引用任何备选标题。
    hit = any((p.get("title") or "")[:6] in answer for p in primary)
    assert hit or any((p.get("brand") or "") in answer for p in primary), (
        f"回答未引用首选商品: {[p.get('title', '')[:12] for p in primary]} | {answer[:60]}")
    # 同品牌/同系列商品的前 6 个字经常完全相同（例如同一口红系列不同色号），
    # 不能把首选标题的共同前缀误判成“回答引用备选”。只检查能和全部首选区分开的
    # 备选标识；没有可区分标识的同系列变体由卡片而不是文本名称区分。
    primary_titles = [p.get("title") or "" for p in primary]
    alternative_markers = []
    for product in alternatives:
        title = product.get("title") or ""
        marker = next((title[:size] for size in (12, 18, 24)
                       if len(title) >= size and all(title[:size] not in item for item in primary_titles)), "")
        if marker:
            alternative_markers.append(marker)
    assert not any(marker in answer for marker in alternative_markers), (
        f"回答引用了可区分的备选商品: {[p.get('title', '')[:12] for p in alternatives]} | {answer[:60]}")


@pytest.mark.integration
def test_deep_think_shopping_action_requires_login_without_free_loop():
    """深度思考不授予交易权限，也不让纯加购请求进入自由工具循环。"""
    client = TestClient(app)
    with client.stream("POST", "/api/recommend/stream", json={
        "user_id": "it_sku", "message": "把这个加入购物车", "deep_think": True,
    }) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    d = _last_result(raw)
    assert d.get("agent_loop") is not True, "纯购物动作不应进入自由 ReAct Loop"
    actions = d.get("actions") or []
    assert any(action.get("type") == "login" for action in actions), actions
    assert "登录" in (d.get("answer") or "")
