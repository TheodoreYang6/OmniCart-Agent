"""ShopActionAgent (Phase 2) 编排层测试 —— 加购/多SKU/pending/下单/确认/地址/全部/兜底。

全部用内存 fake（conv_svc / cart_repo / product_repo / address_repo），无需 PG。
文案与 legacy agent_stream 对齐。
"""

from types import SimpleNamespace

import pytest

from app.framework.tools import ToolContext
from app.schemas.cart import Cart, CartItem, CartItemUpdate
from app.schemas.product import Product, Sku


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
        self.cleared = False

    async def aget_cart(self, user_id="u1"):
        return self.cart

    async def aadd_item(self, item_create, user_id="u1", title="", brand="", price=0.0,
                        image_url="", sku_label=""):
        ci = CartItem(
            cart_item_id=f"c{len(self.cart.items) + 1}", product_id=item_create.product_id,
            sku_id=item_create.sku_id, sku_label=sku_label, title=title, brand=brand,
            price=price, quantity=item_create.quantity,
        )
        self.cart.items.append(ci)
        return ci

    async def aremove_item(self, cart_item_id, user_id="u1"):
        self.cart.items = [i for i in self.cart.items if i.cart_item_id != cart_item_id]
        return True

    async def aupdate_item(self, cart_item_id, upd: CartItemUpdate, user_id="u1"):
        return None

    async def aclear_cart(self, user_id="u1"):
        self.cart.items = []
        self.cleared = True
        return True


class _FakeProd:
    def __init__(self, products):
        self._p = products

    def get_by_id(self, pid):
        return self._p.get(pid)

    def resolve_image_url(self, pid, base_url=""):
        return ""


class _FakeAddr:
    def __init__(self, addrs):
        self._a = addrs

    def list(self, uid):
        return list(self._a)


def _p_single():
    return Product(product_id="P1", title="速溶咖啡", brand="雀巢",
                   category="食品饮料", base_price=99.0, skus=[])


def _p_multi():
    return Product(product_id="P2", title="精华", brand="兰蔻",
                   category="美妆护肤", base_price=500.0,
                   skus=[Sku(sku_id="s30", properties={"容量": "30ml"}, price=500.0),
                         Sku(sku_id="s50", properties={"容量": "50ml"}, price=700.0)])


_ADDR = {"name": "张三", "phone": "13800000000", "province": "北京", "city": "北京",
         "district": "海淀", "detail": "中关村1号", "is_default": True}


@pytest.fixture
def env(monkeypatch):
    conv = _FakeConv()
    cart = _FakeCart()
    prod = _FakeProd({"P1": _p_single(), "P2": _p_multi()})
    addr = _FakeAddr([dict(_ADDR)])
    monkeypatch.setattr("app.services.conversation_service.get_conversation_service", lambda: conv)
    monkeypatch.setattr("app.repositories.pg_cart_repo.get_cart_repo", lambda: cart)
    monkeypatch.setattr("app.repositories.product_repo.get_product_repo", lambda: prod)
    monkeypatch.setattr("app.repositories.address_repo.get_address_repo", lambda: addr)
    return SimpleNamespace(conv=conv, cart=cart, prod=prod, addr=addr)


async def _run(msg: str):
    from app.agents.shop_action_agent import ShopActionAgent

    ctx = ToolContext(user_id="u1", conversation_id="cid1", args_raw=msg)
    return await ShopActionAgent().handle(msg, ctx)


# ---- add ----

async def test_add_single_from_focus(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("加入购物车")
    assert res.ok and "已把" in res.message and "加入购物车" in res.message
    assert len(env.cart.cart.items) == 1 and env.cart.cart.items[0].product_id == "P1"


async def test_add_multi_sku_prompts_and_writes_pending(env):
    env.conv._snap["focus_product"] = {"product_id": "P2", "title": "精华", "brand": "兰蔻", "price": 500}
    res = await _run("加购")
    assert "个规格，选哪个" in res.message
    assert any(a["type"] == "sku_option" for a in res.actions)
    assert env.conv._snap.get("pending_sku_product", {}).get("product_id") == "P2"
    assert len(env.cart.cart.items) == 0  # 尚未加入


async def test_pending_sku_resolves(env):
    env.conv._snap["pending_sku_product"] = {"product_id": "P2", "title": "精华", "brand": "兰蔻", "base_price": 500}
    res = await _run("要30ml的")
    assert res.ok and "加入购物车" in res.message
    assert len(env.cart.cart.items) == 1 and env.cart.cart.items[0].sku_id == "s30"
    assert env.conv._snap.get("pending_sku_product") is None


async def test_add_all(env):
    env.conv._snap["last_products"] = [
        {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99},
        {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99},
    ]
    res = await _run("全部加入")
    assert "已把 2 件商品加入购物车" in res.message
    assert len(env.cart.cart.items) == 2


# ---- order preview / confirm ----

async def test_order_preview_with_address(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("下单")
    assert "订单确认" in res.message and "确认下单吗？" in res.message
    labels = [a["label"] for a in res.actions]
    assert "确认下单" in labels and "修改地址" in labels
    assert env.conv._snap.get("pending_order_items")


async def test_order_preview_without_address(env):
    env.addr._a = []
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("下单")
    assert "请先设置收货地址" in res.message
    assert res.actions and res.actions[0]["type"] == "address_form"


async def test_confirm_focus_does_not_clear_cart(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("确认下单")
    assert "下单成功" in res.message
    assert env.cart.cleared is False


async def test_confirm_from_cart_clears(env):
    env.cart.cart.items.append(
        CartItem(cart_item_id="c1", product_id="P1", title="速溶咖啡", brand="雀巢",
                 price=99, quantity=1, selected=True)
    )
    res = await _run("确认")
    assert "下单成功" in res.message
    assert env.cart.cleared is True


async def test_confirm_without_address(env):
    env.addr._a = []
    env.cart.cart.items.append(
        CartItem(cart_item_id="c1", product_id="P1", title="速溶咖啡", brand="雀巢",
                 price=99, quantity=1, selected=True)
    )
    res = await _run("确认下单")
    assert "还没有收货地址" in res.message


# ---- address / fallback / pure cart ----

async def test_address_prompt(env):
    res = await _run("修改地址")
    assert "填写新地址" in res.message
    assert res.actions and res.actions[0]["type"] == "address_form"


async def test_fallback(env):
    res = await _run("你觉得呢")
    assert "问欧米" in res.message


async def test_pure_cart_view_still_works(env):
    res = await _run("看看购物车")
    assert "购物车" in res.message
