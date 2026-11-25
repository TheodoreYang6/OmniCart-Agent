"""User isolation and checked delivery against a migrated PostgreSQL database."""

from secrets import token_hex

import httpx
import pytest

from app.api import agent_stream
from app.core.config import settings
from app.core.database import get_session_sync
from app.framework.tools import ToolContext
from app.main import app
from app.providers.tools.order import OrderCancelTool, OrderDetailTool
from app.repositories.conversation_repo import get_conversation_repo
from app.repositories.order_repo import get_order_repo
from app.schemas.workflow import WorkflowState
from app.services.checkout_service import persist_order
from app.workflow import graph

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not settings.use_postgres, reason="requires PostgreSQL")]


async def _buyer(client):
    response = await client.post("/api/auth/register", json={
        "username": "qa_" + token_hex(8), "password": token_hex(16),
    })
    assert response.status_code == 200
    return response.json()["user_id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_two_buyers_cannot_read_or_mutate_each_others_data(monkeypatch):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://local") as owner, httpx.AsyncClient(
        transport=transport, base_url="http://local",
    ) as other:
        user_a, user_b = await _buyer(owner), await _buyer(other)
        oid = await persist_order(user_a, [{"product_id": "qa", "title": "QA", "price": 3, "quantity": 1}], 3)
        conv = await get_conversation_repo().acreate(user_a, "qa-" + token_hex(6))
        cid = conv.conversation_id
        ctx = ToolContext(user_id=user_b)
        assert not (await OrderDetailTool().run(ctx, oid)).ok
        assert not (await OrderCancelTool().run(ctx, oid)).ok
        assert (await get_order_repo().aget(oid, user_id=user_a))["status"] == "pending"
        repo = get_conversation_repo()
        assert await repo.aupdate(cid, user_id=user_b, title="mutated") is None
        with pytest.raises(LookupError):
            await repo.aappend_message(cid, user_b, "foreign", "assistant", "foreign")
        assert (await other.get(f"/api/conversations/{cid}/messages")).status_code == 404
        assert (await other.put(f"/api/preferences?conversation_id={cid}", json={"budget_max": 1})).status_code == 404
        assert (await other.delete(f"/api/conversations/{cid}")).status_code == 404
        assert (await owner.get(f"/api/conversations/{cid}")).json()["title"] == conv.title
        assert (await owner.get(f"/api/conversations/{cid}/messages")).json()["messages"] == []
        for method, endpoint in [
            ("GET", "/api/observability/traces"), ("DELETE", "/api/observability/traces"),
            ("POST", "/api/eval/run"), ("POST", "/api/eval/rag/experiment"),
            ("GET", "/eval"), ("POST", "/api/admin/payments/reconcile"),
        ]:
            assert (await other.request(method, endpoint, json={})).status_code == 403
        monkeypatch.setattr(settings, "admin_user_ids", user_a)
        assert (await owner.get("/api/observability/traces")).status_code == 200
        assert (await OrderCancelTool().run(ToolContext(user_id=user_a), oid)).ok


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("bad_text", [
    "小米 Buds A100 只要 ¥99.99",
    "小米 Buds A100 ¥199.90，也可以买苹果 AirPods Z500 ¥199.90",
    "小米 Buds A100 ¥199.90，也可以买小米 Buds A999 ¥199.90",
    "小米 Buds A100 ¥199.90，可以降低血糖",
])
async def test_guarded_stream_and_history_match(monkeypatch, bad_text):
    async def fake_workflow(**_):
        return WorkflowState(
            intent="recommend", retrieved_products=[
                {"product_id": "qa-p1", "title": "小米 Buds A100 蓝牙耳机", "brand": "小米", "price": 199.9,
                 "filter_bucket": "primary"},
                {"product_id": "qa-p2", "title": "苹果 AirPods Z500", "brand": "Apple", "price": 199.9,
                 "filter_bucket": "excluded"},
            ], structured_retrieval_report={"version": "v9"},
        )

    async def generate(_):
        yield bad_text

    from types import SimpleNamespace
    from json import loads
    monkeypatch.setattr(agent_stream, "run_workflow", fake_workflow)
    monkeypatch.setattr(graph, "get_response_agent", lambda: SimpleNamespace(generate_stream=generate))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        await _buyer(client)
        response = await client.post("/api/recommend/stream", json={"message": "推荐耳机", "session_id": token_hex(6)})
        assert response.status_code == 200
        events = [(event.removeprefix("event: "), loads(data.removeprefix("data: ")))
                  for block in response.text.strip().split("\n\n") if block.startswith("event:")
                  for event, data in [block.splitlines()]]
        types = [name for name, _ in events]
        assert types.index("recommendations") < types.index("token") < types.index("result")
        result = next(payload for name, payload in events if name == "result")
        body = "".join(payload["text"] for name, payload in events if name == "token")
        assert bad_text not in body and body == result["answer"]
        assert "¥199.90" in body and result["harness_report"]["fallback_used"]
        history = await client.get("/api/conversations/" + result["conversation_id"] + "/messages")
        assert history.json()["messages"][-1]["content"] == body


@pytest.mark.asyncio(loop_scope="module")
async def test_alipay_replay_and_verified_refunds(monkeypatch):
    import asyncio
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy import func, select

    from app.api import report_payments
    from app.models.order import OrderModel
    from app.models.report_order import AlipayRefundModel, ReportOrderModel
    from app.services import alipay_refunds, payment_settlement

    now = datetime.now(timezone.utc)
    order_id, trade_no = token_hex(16), token_hex(16)
    provider = SimpleNamespace(
        app_id="qa-app", seller_id="qa-seller", verify_notification=lambda fields: fields.get("sign") == "fixture",
        query_refund=AsyncMock(), query=AsyncMock(), close=AsyncMock(),
    )
    monkeypatch.setattr(settings, "report_payment_mode", "sandbox")
    for module in (report_payments, alipay_refunds, payment_settlement):
        monkeypatch.setattr(module, "_provider", lambda: provider)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        user = await _buyer(client)
        monkeypatch.setattr(settings, "admin_user_ids", user)
        async with get_session_sync()() as session:
            session.add(ReportOrderModel(
                order_id=order_id, user_id=user, kind="cart", amount_fen=300,
                channel="alipay", environment="sandbox", app_id=provider.app_id, seller_id=provider.seller_id,
                status="pending", report={"items": [], "address": {}, "item_versions": {}},
                created_at=now - timedelta(minutes=30), expires_at=now - timedelta(minutes=1),
            ))
            await session.commit()

        waiting = {"code": "10000", "out_trade_no": order_id, "total_amount": "3.00", "trade_status": "WAIT_BUYER_PAY"}
        provider.query.side_effect = [waiting, {**waiting, "trade_status": "TRADE_CLOSED"}]
        endpoint = "/api/cart-payments/orders/" + order_id
        assert (await client.post(endpoint + "/refresh")).json()["status"] == "closed"
        provider.close.assert_awaited_once_with(order_id)

        fields = {
            "app_id": provider.app_id, "seller_id": provider.seller_id, "out_trade_no": order_id,
            "total_amount": "3.00", "trade_no": trade_no, "trade_status": "TRADE_SUCCESS", "sign": "fixture",
        }
        responses = await asyncio.gather(*(
            client.post("/api/report-payments/alipay/notify", data=fields) for _ in range(2)
        ))
        assert [response.text for response in responses] == ["success", "success"]
        assert (await client.get(endpoint)).json()["status"] == "paid"
        assert not (await OrderCancelTool().run(ToolContext(user_id=user), order_id)).ok

        refund_url = f"/api/admin/payments/{order_id}/refund/reconcile"
        receipt = {"code": "10000", "out_trade_no": order_id, "trade_no": trade_no}
        provider.query_refund.return_value = {**receipt, "refund_status": "REFUND_PROCESSING"}
        assert (await client.post(refund_url, json={"request_no": "first"})).json()["verified"] is False
        assert (await client.get(endpoint)).json()["status"] == "paid"
        receipt["refund_status"] = "REFUND_SUCCESS"
        provider.query_refund.return_value = {**receipt, "out_request_no": "first", "refund_amount": "1.00"}
        for _ in range(2):
            response = await client.post(refund_url, json={"request_no": "first"})
            assert response.json()["status"] == "partially_refunded"
            assert response.json()["refunded_fen"] == 100
        provider.query_refund.return_value = {**receipt, "out_request_no": "second", "refund_amount": "2.00"}
        assert (await client.post(refund_url, json={"request_no": "second"})).json()["status"] == "refunded"
        assert (await client.get(endpoint)).json()["status"] == "refunded"
        reconciled = await client.post("/api/admin/payments/reconcile", json={"order_ids": [order_id]})
        assert reconciled.json() == [{"order_id": order_id, "status": "refunded"}]
        async with get_session_sync()() as session:
            assert (await session.get(OrderModel, order_id)).status == "refunded"
            assert await session.scalar(select(func.count()).select_from(OrderModel).where(
                OrderModel.order_id == order_id,
            )) == 1
            assert await session.scalar(select(func.count()).select_from(AlipayRefundModel).where(
                AlipayRefundModel.order_id == order_id,
            )) == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_cart_quote_blocks_stale_confirm_and_demo_lifecycle(monkeypatch):
    """确认前变更购物车/地址必须重新报价；demo 支付幂等；过期关单后可重新报价。"""
    from datetime import datetime, timedelta, timezone

    from app.models.product import ProductModel
    from app.models.report_order import ReportOrderModel

    monkeypatch.setattr(settings, "report_payment_mode", "demo")
    product_id = "qa-pay-" + token_hex(6)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://local") as client, httpx.AsyncClient(
        transport=transport, base_url="http://local",
    ) as other:
        user = await _buyer(client)
        await _buyer(other)
        async with get_session_sync()() as session:
            session.add(ProductModel(
                product_id=product_id, title="QA 支付测试耳机", brand="小米",
                category="数码电子", sub_category="真无线耳机", base_price=199.9, skus=[],
            ))
            await session.commit()

        first_addr = (await client.post("/api/addresses", json={
            "name": "收一", "phone": "13800000001", "province": "上海市", "city": "上海市",
            "district": "浦东新区", "detail": "测试路1号", "is_default": True,
        })).json()["address_id"]
        assert (await client.post("/api/cart/items", json={"product_id": product_id, "quantity": 1})).status_code == 200

        quote = (await client.post("/api/cart-payments/orders", json={"item_ids": []})).json()
        assert quote["status"] == "quoted" and quote["amount_fen"] == 19990
        assert quote["address"]["name"] == "收一"
        order_id = quote["order_id"]
        cart_item = (await client.get("/api/cart")).json()["items"][0]["cart_item_id"]

        # 确认前改数量 → 409 要求重新报价（任何行触碰都会刷新版本号）
        await client.put(f"/api/cart/items/{cart_item}", json={"quantity": 2})
        assert (await client.post(f"/api/cart-payments/orders/{order_id}/confirm", json={"confirmed": True})).status_code == 409

        # 重新报价后，确认前改默认地址 → 同样 409（本轮不动购物车，隔离出地址检测）
        second_quote = (await client.post("/api/cart-payments/orders", json={"item_ids": []})).json()
        assert second_quote["amount_fen"] == 39980  # 数量 2
        await client.post("/api/addresses", json={
            "name": "收二", "phone": "13800000002", "province": "北京市", "city": "北京市",
            "district": "朝阳区", "detail": "测试路2号", "is_default": True,
        })
        assert (await client.post(f"/api/cart-payments/orders/{second_quote['order_id']}/confirm", json={"confirmed": True})).status_code == 409

        # 再次重新报价（地址已稳定）→ 确认放行
        third_quote = (await client.post("/api/cart-payments/orders", json={"item_ids": []})).json()
        assert third_quote["address"]["name"] == "收二"
        confirmed = (await client.post(f"/api/cart-payments/orders/{third_quote['order_id']}/confirm", json={"confirmed": True})).json()
        assert confirmed["status"] == "pending"
        # 重复确认幂等：状态不变、不重复扣款
        assert (await client.post(f"/api/cart-payments/orders/{third_quote['order_id']}/confirm", json={"confirmed": True})).json()["status"] == "pending"

        # 他人无法查看或支付这笔订单
        assert (await other.get(f"/api/cart-payments/orders/{third_quote['order_id']}")).status_code == 404
        assert (await other.post(f"/api/cart-payments/orders/{third_quote['order_id']}/demo-pay", json={"confirmed": True})).status_code == 404

        paid = (await client.post(f"/api/cart-payments/orders/{third_quote['order_id']}/demo-pay", json={"confirmed": True})).json()
        assert paid["status"] == "paid" and paid["trade_no"]
        assert (await client.post(f"/api/cart-payments/orders/{third_quote['order_id']}/demo-pay", json={"confirmed": True})).json()["status"] == "paid"

        # 履约一致性：购物车清空、订单带收货地址
        assert (await client.get("/api/cart")).json()["items"] == []
        order = (await client.get("/api/orders")).json()["orders"][0]
        assert order["order_id"] == third_quote["order_id"] and order["status"] == "paid"
        assert order["shipping_address"]["name"] == "收二"

        # 过期关单后可重新报价：旧单 closed，新单 quoted
        assert (await client.post("/api/cart/items", json={"product_id": product_id, "quantity": 1})).status_code == 200
        second = (await client.post("/api/cart-payments/orders", json={"item_ids": []})).json()
        async with get_session_sync()() as session:
            row = await session.get(ReportOrderModel, second["order_id"])
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()
        assert (await client.post(f"/api/cart-payments/orders/{second['order_id']}/confirm", json={"confirmed": True})).status_code == 409
        # quoted 单未开过收银台，refresh 原样返回；它不阻塞重新报价
        assert (await client.post(f"/api/cart-payments/orders/{second['order_id']}/refresh")).json()["status"] == "quoted"

        # pending 过期：refresh 由 demo 本地核销关单，之后可重新报价
        third = (await client.post("/api/cart-payments/orders", json={"item_ids": []})).json()
        assert third["status"] == "quoted" and third["order_id"] != second["order_id"]
        assert (await client.post(f"/api/cart-payments/orders/{third['order_id']}/confirm", json={"confirmed": True})).json()["status"] == "pending"
        async with get_session_sync()() as session:
            row = await session.get(ReportOrderModel, third["order_id"])
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()
        assert (await client.post(f"/api/cart-payments/orders/{third['order_id']}/confirm", json={"confirmed": True})).status_code == 409
        assert (await client.post(f"/api/cart-payments/orders/{third['order_id']}/refresh")).json()["status"] == "closed"
        fourth = (await client.post("/api/cart-payments/orders", json={"item_ids": []})).json()
        assert fourth["status"] == "quoted" and fourth["order_id"] != third["order_id"]


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("kind", ["cart", "report"])
async def test_buyer_can_recover_provider_payment_for_closed_order(monkeypatch, kind):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.models.report_order import ReportOrderModel
    from app.services import payment_settlement

    order_id, trade_no = token_hex(16), token_hex(16)
    trade = {
        "code": "10000", "out_trade_no": order_id, "total_amount": "1.99",
        "trade_status": "TRADE_SUCCESS", "trade_no": trade_no,
    }
    provider = SimpleNamespace(app_id="qa-app", seller_id="qa-seller", query=AsyncMock(return_value=trade))
    monkeypatch.setattr(settings, "report_payment_mode", "sandbox")
    monkeypatch.setattr(payment_settlement, "_provider", lambda: provider)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://local") as buyer, httpx.AsyncClient(
        transport=transport, base_url="http://local",
    ) as other:
        user_id = await _buyer(buyer)
        await _buyer(other)
        now = datetime.now(timezone.utc)
        payload = (
            {"items": [], "address": {}, "item_versions": {}}
            if kind == "cart"
            else {"category": "headphones", "budget_fen": 10000, "candidate_count": 2}
        )
        async with get_session_sync()() as session:
            session.add(ReportOrderModel(
                order_id=order_id, user_id=user_id, kind=kind, channel="web", environment="sandbox",
                app_id=provider.app_id, seller_id=provider.seller_id, status="closed", amount_fen=199,
                report=payload, created_at=now - timedelta(hours=1), expires_at=now - timedelta(minutes=30),
            ))
            await session.commit()

        endpoint = f"/api/{kind}-payments/orders/{order_id}/refresh"
        assert (await other.post(endpoint)).status_code == 404
        provider.query.assert_not_awaited()
        response = await buyer.post(endpoint)
        assert response.status_code == 200
        assert response.json()["status"] == "paid"
        assert response.json()["trade_no"] == trade_no
        provider.query.assert_awaited_once_with(order_id)


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("gateway_status", ["TRADE_SUCCESS", "TRADE_CLOSED"])
async def test_expired_cart_stays_pending_until_alipay_confirms(monkeypatch, gateway_status):
    """An outage cannot free the payment slot while the original charge is uncertain."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.models.product import ProductModel
    from app.models.report_order import ReportOrderModel
    from app.services import checkout_payment as checkout_payment_module
    from app.services import payment_settlement

    product_id = "qa-pay-" + token_hex(6)
    provider = SimpleNamespace(
        app_id="qa-app",
        seller_id="qa-seller",
        query=AsyncMock(side_effect=httpx.ConnectError("gateway down")),
        checkout_url=lambda order: "https://example.invalid/checkout",
    )
    monkeypatch.setattr(settings, "report_payment_mode", "sandbox")
    monkeypatch.setattr(checkout_payment_module, "_provider", lambda: provider)
    monkeypatch.setattr(payment_settlement, "_provider", lambda: provider)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
        user = await _buyer(client)
        async with get_session_sync()() as session:
            session.add(ProductModel(
                product_id=product_id, title="QA 支付测试耳机", brand="小米",
                category="数码电子", sub_category="真无线耳机", base_price=199.9, skus=[],
            ))
            await session.commit()
        assert (await client.post("/api/addresses", json={
            "name": "收三", "phone": "13800000003", "province": "广州市", "city": "广州市",
            "district": "天河区", "detail": "测试路3号", "is_default": True,
        })).status_code == 200
        assert (await client.post("/api/cart/items", json={"product_id": product_id, "quantity": 1})).status_code == 200

        quote_path = "/api/cart-payments/orders"
        sale = await client.post(quote_path, json={"item_ids": []})
        alternative = await client.post(quote_path, json={"item_ids": []})
        stale_id = sale.json()["order_id"]
        stale_url = f"{quote_path}/{stale_id}"
        alternative_url = f"{quote_path}/{alternative.json()['order_id']}"
        assert (await client.post(stale_url + "/confirm", json={"confirmed": True})).status_code == 200
        async with get_session_sync()() as session:
            stale = await session.get(ReportOrderModel, stale_id)
            stale.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            await session.commit()

        assert (await client.post(quote_path, json={"item_ids": []})).status_code == 502
        assert (await client.get(stale_url)).json()["status"] == "pending"
        assert (await client.get("/api/cart-payments/active")).json()["order_id"] == stale_id
        assert (await client.post(alternative_url + "/confirm", json={"confirmed": True})).status_code == 409

        provider.query.side_effect = None
        provider.query.return_value = {
            "code": "10000", "out_trade_no": stale_id, "total_amount": "199.90",
            "trade_status": gateway_status, "trade_no": token_hex(16),
        }
        retry = await client.post(quote_path, json={"item_ids": []})
        assert retry.status_code == 201
        if gateway_status == "TRADE_SUCCESS":
            assert retry.json()["order_id"] == stale_id
            assert retry.json()["status"] == "paid"
            assert (await client.post(alternative_url + "/confirm", json={"confirmed": True})).status_code == 409
            orders = (await client.get("/api/orders")).json()["orders"]
            assert [(order["order_id"], order["status"]) for order in orders] == [(stale_id, "paid")]
        else:
            assert (await client.get(stale_url)).json()["status"] == "closed"
            assert retry.json()["order_id"] != stale_id
            assert retry.json()["status"] == "quoted"
            replacement_url = f"{quote_path}/{retry.json()['order_id']}"
            assert (await client.post(replacement_url + "/confirm", json={"confirmed": True})).status_code == 200
