"""Phase 2b: 订单闭环（list / detail / cancel / track / pay）+ 库存查询集成测试。

fakes: conv_svc / cart_repo / product_repo / address_repo / order_repo /
inventory/payment/logistics providers。全内存驱动，无需 PG。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.framework.tools import ToolContext
from app.schemas.cart import Cart, CartItem, CartItemUpdate
from app.schemas.product import Product


# ---- fakes ----

class _FakeConv:
    def __init__(self, snap=None):
        self._snap = dict(snap or {})

    async def get_context_snapshot(self, cid):
        return dict(self._snap)

    async def aupdate_context_snapshot(self, cid, updates):
        self._snap.update(updates)


class _FakeCart:
    def __init__(self, items=None):
        self.cart = Cart(user_id="u1", items=items or [])

    async def aget_cart(self, user_id="u1"):
        return self.cart

    async def aadd_item(self, *a, **kw):
        return None

    async def aremove_item(self, cart_item_id, user_id="u1"):
        return True

    async def aupdate_item(self, cart_item_id, upd: CartItemUpdate, user_id="u1"):
        return None

    async def aclear_cart(self, user_id="u1"):
        self.cart.items = []
        return True


class _FakeProd:
    def __init__(self, products):
        self._p = products

    def get_by_id(self, pid):
        return self._p.get(pid)

    def resolve_image_url(self, pid, base_url=""):
        return ""


class _FakeAddr:
    def __init__(self, addrs=None):
        self._a = addrs or []

    def list(self, uid):
        return list(self._a)


class _FakeOrderRepo:
    def __init__(self):
        self._orders: dict[str, dict] = {}

    def add(self, order: dict) -> None:
        self._orders[order["order_id"]] = dict(order)

    async def alist_by_user(self, user_id, limit=20):
        items = [o for o in self._orders.values() if o.get("user_id") == user_id]
        items.sort(key=lambda o: o.get("created_at", ""), reverse=True)
        return items[:limit]

    async def aget(self, order_id):
        o = self._orders.get(order_id)
        return dict(o) if o else None

    async def aupdate_status(self, order_id, status):
        if order_id not in self._orders:
            return False
        self._orders[order_id]["status"] = status
        return True


class _FakeInv:
    def __init__(self, result=None):
        self._r = result or {"in_stock": True, "quantity": 100, "eta": "1-3天", "level": "in_stock"}

    async def check(self, product_id, sku_id=None):
        return dict(self._r)


class _FakePay:
    async def pay(self, order_id, method="mock"):
        return {"status": "paid", "txn_id": "TXN-TESTTEST", "error": ""}


class _FakeLog:
    async def track(self, order_id, created_at=None):
        return {
            "state": "运输中",
            "nodes": [
                {"name": "已揽收", "time": "2026-07-22 09:00", "done": True},
                {"name": "运输中", "time": "2026-07-22 12:00", "done": True},
                {"name": "派送中", "time": "", "done": False},
                {"name": "已签收", "time": "", "done": False},
            ],
            "eta": "约 12 小时后进入下一节点",
        }


def _order(oid: str, status: str = "pending", user_id: str = "u1", total: float = 100.0):
    return {
        "order_id": oid,
        "user_id": user_id,
        "items": [{"product_id": "P1", "title": "降噪耳机", "brand": "Sony",
                   "price": total, "quantity": 1}],
        "total_price": total,
        "status": status,
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
    }


def _p_single():
    return Product(product_id="P1", title="速溶咖啡", brand="雀巢",
                   category="食品饮料", base_price=99.0, skus=[])


@pytest.fixture
def env(monkeypatch):
    conv = _FakeConv()
    cart = _FakeCart()
    prod = _FakeProd({"P1": _p_single()})
    addr = _FakeAddr()
    orders = _FakeOrderRepo()
    inv = _FakeInv()
    pay = _FakePay()
    log = _FakeLog()
    monkeypatch.setattr("app.services.conversation_service.get_conversation_service", lambda: conv)
    monkeypatch.setattr("app.repositories.pg_cart_repo.get_cart_repo", lambda: cart)
    monkeypatch.setattr("app.repositories.product_repo.get_product_repo", lambda: prod)
    monkeypatch.setattr("app.repositories.address_repo.get_address_repo", lambda: addr)
    monkeypatch.setattr("app.repositories.order_repo.get_order_repo", lambda: orders)
    monkeypatch.setattr("app.providers.tools.mocks.get_inventory_provider", lambda: inv)
    monkeypatch.setattr("app.providers.tools.mocks.get_payment_provider", lambda: pay)
    monkeypatch.setattr("app.providers.tools.mocks.get_logistics_provider", lambda: log)
    return SimpleNamespace(conv=conv, cart=cart, prod=prod, addr=addr,
                            orders=orders, inv=inv, pay=pay, log=log)


async def _run(msg: str):
    from app.agents.shop_action_agent import ShopActionAgent

    ctx = ToolContext(user_id="u1", conversation_id="cid1", args_raw=msg)
    return await ShopActionAgent().handle(msg, ctx)


# ---- order.list ----

async def test_order_list_populates_last_orders(env):
    env.orders.add(_order("ORD-11111111", status="pending"))
    env.orders.add(_order("ORD-22222222", status="paid"))
    res = await _run("我的订单")
    assert "你的订单" in res.message
    assert "ORD-11111111" in res.message and "ORD-22222222" in res.message
    assert set(env.conv._snap.get("last_orders", [])) == {"ORD-11111111", "ORD-22222222"}


async def test_order_list_empty(env):
    res = await _run("我的订单")
    assert "还没有订单" in res.message


# ---- order.detail ----

async def test_order_detail_uses_last_orders(env):
    env.orders.add(_order("ORD-AAAAAAAA", status="pending"))
    env.conv._snap["last_orders"] = ["ORD-AAAAAAAA"]
    res = await _run("订单详情")
    assert "ORD-AAAAAAAA" in res.message and "状态" in res.message


async def test_order_detail_without_orders(env):
    res = await _run("订单详情")
    assert not res.ok and "查看订单" in res.message


# ---- order.cancel ----

async def test_order_cancel_ordinal(env):
    env.orders.add(_order("ORD-BBBBBBBB", status="pending"))
    env.orders.add(_order("ORD-CCCCCCCC", status="pending"))
    env.conv._snap["last_orders"] = ["ORD-BBBBBBBB", "ORD-CCCCCCCC"]
    res = await _run("取消第2个")
    assert "已取消" in res.message and "ORD-CCCCCCCC" in res.message
    assert env.orders._orders["ORD-CCCCCCCC"]["status"] == "cancelled"


async def test_order_cancel_already_cancelled(env):
    env.orders.add(_order("ORD-DDDDDDDD", status="cancelled"))
    env.conv._snap["last_orders"] = ["ORD-DDDDDDDD"]
    res = await _run("取消订单")
    assert not res.ok and "已取消" in res.message


async def test_order_cancel_paid_has_refund_copy(env):
    """P2-1: 已支付订单取消附退款语义。"""
    env.orders.add(_order("ORD-REFUND01", status="paid"))
    env.conv._snap["last_orders"] = ["ORD-REFUND01"]
    res = await _run("取消订单")
    assert res.ok and "原路退回" in res.message
    assert res.data.get("refund") is True


async def test_order_cancel_shipped_blocked(env):
    """P2-1: 已发货拒绝取消。"""
    env.orders.add(_order("ORD-SHIPPED1", status="shipped"))
    env.conv._snap["last_orders"] = ["ORD-SHIPPED1"]
    res = await _run("取消订单")
    assert not res.ok and "无法取消" in res.message
    assert env.orders._orders["ORD-SHIPPED1"]["status"] == "shipped"


async def test_order_track_paid_preparing_copy(env):
    """P2-4: 刚支付首节点未达 → 备货文案。"""
    class _FreshLog:
        async def track(self, order_id, created_at=None):
            return {"state": "待发货", "nodes": [
                {"name": "已揽收", "time": "", "done": False},
                {"name": "运输中", "time": "", "done": False},
            ], "eta": ""}

    import pytest as _pytest  # noqa: F401
    env.log_override = _FreshLog()
    # 重新 patch logistics provider
    import app.providers.tools.mocks as _mocks
    _orig = _mocks.get_logistics_provider
    _mocks.get_logistics_provider = lambda: env.log_override
    try:
        env.orders.add(_order("ORD-FRESHPAY", status="paid"))
        env.conv._snap["last_orders"] = ["ORD-FRESHPAY"]
        res = await _run("查物流")
        assert "已支付，商家备货中" in res.message
    finally:
        _mocks.get_logistics_provider = _orig


# ---- order.track ----

async def test_order_track_paid(env):
    env.orders.add(_order("ORD-EEEEEEEE", status="paid"))
    env.conv._snap["last_orders"] = ["ORD-EEEEEEEE"]
    res = await _run("查物流")
    assert "物流轨迹" in res.message and "已揽收" in res.message
    assert "ORD-EEEEEEEE" in res.message


async def test_order_track_pending_no_logistics(env):
    env.orders.add(_order("ORD-FFFFFFFF", status="pending"))
    env.conv._snap["last_orders"] = ["ORD-FFFFFFFF"]
    res = await _run("物流")
    assert not res.ok and "还未支付" in res.message


# ---- order.pay ----

async def test_order_pay_pending(env):
    env.orders.add(_order("ORD-99999999", status="pending"))
    env.conv._snap["last_orders"] = ["ORD-99999999"]
    res = await _run("支付订单")
    assert "支付成功" in res.message and "TXN-TESTTEST" in res.message
    assert env.orders._orders["ORD-99999999"]["status"] == "paid"


async def test_order_pay_already_paid(env):
    env.orders.add(_order("ORD-88888888", status="paid"))
    env.conv._snap["last_orders"] = ["ORD-88888888"]
    res = await _run("支付订单")
    assert not res.ok and "已支付" in res.message


# ---- check_inventory ----

async def test_check_inventory_in_stock(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("有货吗")
    assert res.ok and "雀巢 速溶咖啡" in res.message and "有货" in res.message


async def test_check_inventory_low(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    env.inv._r = {"in_stock": True, "quantity": 3, "eta": "3-5天", "level": "low"}
    res = await _run("库存")
    assert "低库存" in res.message and "3" in res.message


async def test_check_inventory_out(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    env.inv._r = {"in_stock": False, "quantity": 0, "eta": "", "level": "out"}
    res = await _run("有货吗")
    assert not res.ok or "缺货" in res.message  # ToolResult ok=True but message says 缺货


async def test_check_inventory_no_target(env):
    res = await _run("有货吗")
    assert not res.ok and "请先看看商品" in res.message
