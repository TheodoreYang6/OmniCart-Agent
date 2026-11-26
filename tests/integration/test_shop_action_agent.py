"""ShopActionAgent (Phase 2) 编排层测试 —— 加购/多SKU/pending/下单/确认/地址/全部/兜底。

全部用内存 fake（conv_svc / cart_repo / product_repo / address_repo），无需 PG。
文案与 legacy agent_stream 对齐。
"""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.framework.tools import ToolContext
from app.schemas.cart import Cart, CartItem, CartItemUpdate
from app.schemas.product import Product, Sku


# ---- fakes ----

class _FakeConv:
    def __init__(self, snap=None):
        self._snap = dict(snap or {})

    async def aget_context(self, cid, limit=6, *, user_id):
        return {"context_snapshot": dict(self._snap), "recent_messages": []}

    async def get_context_snapshot(self, cid, *, user_id):
        return dict(self._snap)

    async def aupdate_context_snapshot(self, cid, updates, *, user_id):
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
    # 下单已统一收敛到 checkout_service 持久化；这里保持单测的内存边界，
    # 只验证 ShopActionAgent 的编排、卡片与清车行为，不依赖真实 PostgreSQL。
    async def _persist_order(_user_id, _items, _total):
        return "ORD-TEST-001"
    monkeypatch.setattr("app.services.checkout_service.persist_order", _persist_order)
    return SimpleNamespace(conv=conv, cart=cart, prod=prod, addr=addr)


async def _run(msg: str):
    from app.agents.shop_action_agent import ShopActionAgent

    ctx = ToolContext(user_id="u1", conversation_id="cid1", args_raw=msg)
    return await ShopActionAgent().handle(msg, ctx)


# ---- add ----

async def test_add_single_from_focus(env):
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("加入购物车")
    assert res.ok and "放进购物车" in res.message
    assert len(env.cart.cart.items) == 1 and env.cart.cart.items[0].product_id == "P1"


@pytest.mark.parametrize("message", [
    "帮我加入到购物车吧～",
    "帮我加入到购物车吧~",
    "把这个特别版放进我的购物车吧",
    "这杯咖啡给我留一份，放我的清单里。",
])
async def test_conversational_cart_add_through_stream(env, monkeypatch, message):
    from fastapi import FastAPI

    from app.api import agent_stream
    from app.core.identity import Actor, resolve_public_actor

    async def unexpected_recommendation(**_):
        pytest.fail("Explicit add-to-cart request reached product recommendation")

    async def interpret(capability, prompt, *, system):
        assert capability == "shopping_action"
        assert "询问操作方法" in system and "不得输出 _confirmed" in system
        assert json.loads(prompt)["message"] == message
        assert json.loads(prompt)["products"] == {"p1": {"title": "速溶咖啡", "price": 99}}
        return '{"action":"cart.add","product":["p1"]}'

    monkeypatch.setattr("app.services.chat_shopping_intent.get_model_gateway", lambda: SimpleNamespace(chat=interpret))
    monkeypatch.setattr(agent_stream, "run_workflow", unexpected_recommendation)
    app = FastAPI()
    app.include_router(agent_stream.router)
    app.dependency_overrides[resolve_public_actor] = lambda: Actor("u1", "user")
    env.conv._snap["last_products"] = [
        {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99},
    ]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        response = await client.post("/api/recommend/stream", json={
            "message": message, "conversation_id": "cid1", "session_id": "sid1",
        })
    assert response.status_code == 200
    result_block = next(block for block in response.text.split("\n\n") if block.startswith("event: result\n"))
    result = json.loads(result_block.splitlines()[1].removeprefix("data: "))
    assert result["shop_action"] is True
    assert "放进购物车" in result["answer"]
    assert [(item.product_id, item.quantity) for item in env.cart.cart.items] == [("P1", 1)]


async def test_add_without_target_asks_which_product(env):
    env.conv._snap["last_products"] = [
        {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99},
        {"product_id": "P2", "title": "精华", "brand": "兰蔻", "price": 500},
    ]

    result = await _run("帮我加入到购物车吧～")
    assert not result.ok and "你想加哪款" in result.message
    assert not env.cart.cart.items
    result = await _run("把第 2 款放进购物车")
    assert any(action["type"] == "sku_option" for action in result.actions)
    assert env.conv._snap["pending_sku_product"]["product_id"] == "P2"
    assert not env.cart.cart.items


async def test_add_multi_sku_prompts_and_writes_pending(env):
    env.conv._snap["focus_product"] = {"product_id": "P2", "title": "精华", "brand": "兰蔻", "price": 500}
    res = await _run("加购")
    assert "个规格" in res.message
    assert any(a["type"] == "sku_option" for a in res.actions)
    assert env.conv._snap.get("pending_sku_product", {}).get("product_id") == "P2"
    assert len(env.cart.cart.items) == 0  # 尚未加入


async def test_pending_sku_resolves(env):
    env.conv._snap["pending_sku_product"] = {"product_id": "P2", "title": "精华", "brand": "兰蔻", "base_price": 500}
    res = await _run("要30ml的")
    assert res.ok and "放进购物车" in res.message
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
    assert "确认没问题就下单" in res.message
    labels = [a["label"] for a in res.actions]
    assert "确认下单" in labels and "修改地址" in labels
    assert env.conv._snap.get("pending_order_items")


async def test_order_preview_without_address(env):
    env.addr._a = []
    env.conv._snap["focus_product"] = {"product_id": "P1", "title": "速溶咖啡", "brand": "雀巢", "price": 99}
    res = await _run("下单")
    assert "还差一个收货地址" in res.message
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


@pytest.mark.parametrize("model_reply", [
    '{"action":"cart.add","product":["invented"]}',
    '{"action":"cart.add","product":["p1"],"_confirmed":true}',
    '{"action":"clarify","question":"你指的是哪款？"}',
])
async def test_semantic_cart_route_rejects_unbound_or_ambiguous_actions(env, monkeypatch, model_reply):
    from app.services.chat_shopping_router import run_shopping_turn

    async def interpret(*args, **kwargs):
        return model_reply

    monkeypatch.setattr("app.services.chat_shopping_intent.get_model_gateway", lambda: SimpleNamespace(chat=interpret))
    env.conv._snap["last_products"] = [{"product_id": "P1", "title": "速溶咖啡"}]
    await run_shopping_turn(
        ToolContext(user_id="u1", conversation_id="cid1", args_raw="先别动我的购物车"),
        env.conv, authenticated=True, payment_available=False,
    )
    assert env.cart.cart.items == []


async def test_semantic_route_binds_cart_row_and_reuses_tool_results(env, monkeypatch):
    from app.services.chat_shopping_router import run_shopping_turn

    env.conv._snap["last_products"] = [{"product_id": "P1", "title": "速溶咖啡"}]
    count = 0

    async def interpret(_, prompt, **kwargs):
        nonlocal count
        count += 1
        model_input = json.loads(prompt)
        if count == 1:
            return '{"action":"cart.add","product":["p1"],"quantity":2,"continue_after":true}'
        assert model_input["cart"]["c1"]["quantity"] == 2
        assert model_input["completed"][0]["intent"]["action"] == "cart.add"
        return '{"action":"cart.view"}'

    monkeypatch.setattr("app.services.chat_shopping_intent.get_model_gateway", lambda: SimpleNamespace(chat=interpret))
    result = await run_shopping_turn(
        ToolContext(user_id="u1", conversation_id="cid1", args_raw="给这杯咖啡留两份，再给我看篮子"),
        env.conv, authenticated=True, payment_available=False,
    )
    assert count == 2
    assert result.ok and result.data["shop_card"]["kind"] == "cart_summary"
    assert [(item.product_id, item.quantity) for item in env.cart.cart.items] == [("P1", 2)]


async def test_order_confirmation_is_bound_to_owner_and_status(monkeypatch):
    from fastapi import HTTPException

    from app.services.shop_action_confirmation import offer_order_confirmation, confirm_order_action

    order = {"status": "pending"}

    async def aget(order_id, *, user_id):
        assert (user_id, order_id) == ("buyer", "ORD-1")
        return order

    monkeypatch.setattr("app.repositories.order_repo.get_order_repo", lambda: SimpleNamespace(aget=aget))
    result = await offer_order_confirmation("buyer", "order.cancel", "ORD-1")
    confirmation = result.actions[0]["confirmation"]
    with pytest.raises(HTTPException) as wrong_user:
        await confirm_order_action("another", confirmation)
    assert wrong_user.value.status_code == 400
    order["status"] = "shipped"
    with pytest.raises(HTTPException) as stale:
        await confirm_order_action("buyer", confirmation)
    assert stale.value.status_code == 409


async def test_w30_cart_request_recovers_from_invalid_model_response(env, monkeypatch):
    from app.services.chat_shopping_router import run_shopping_turn

    title = "漫步者 W30 真无线耳机（黑/白/蓝三色可选）"
    env.prod._p["P2"] = Product(
        product_id="P2", title=title, brand="漫步者", category="数码电子", base_price=299,
        skus=[Sku(sku_id=color, properties={"颜色": color}, price=299) for color in ("黑", "白", "蓝")],
    )
    env.conv._snap["focus_product"] = {
        "product_id": "P2", "title": title, "price": 299, "locked_at": "2026-11-25T13:30:00+00:00",
    }
    env.conv._snap["last_products"] = [{"product_id": "P1", "title": "前一轮推荐的咖啡"}]
    answers = iter([
        "好的，我可以帮你加入购物车。",
        '{"action":"cart.add","product":"focus","sku":null,"quantity":null}',
        '{"action":"cart.select_sku","sku":"s3"}',
    ])
    calls = []

    async def interpret(_, prompt, *, system):
        calls.append((json.loads(prompt), system))
        return next(answers)

    monkeypatch.setattr("app.services.chat_shopping_intent.get_model_gateway", lambda: SimpleNamespace(chat=interpret))
    ctx = ToolContext(user_id="u1", conversation_id="cid1", args_raw="帮我加入购物车吧～～～")
    picker = await run_shopping_turn(ctx, env.conv, authenticated=True, payment_available=False)
    assert calls[0][0]["message"] == ctx.args_raw and calls[0][0] == calls[1][0]
    assert "重新判断原消息" in calls[1][1]
    assert {product["title"] for product in calls[0][0]["products"].values()} == {title}
    assert picker.data["shop_card"]["kind"] == "sku_picker"
    assert env.cart.cart.items == []

    ctx.args_raw = "就要蓝色"
    selected = await run_shopping_turn(ctx, env.conv, authenticated=True, payment_available=False)
    assert calls[2][0]["pending_skus"]["s3"] == "蓝"
    assert selected.ok and "放进购物车" in selected.message
    assert [(item.product_id, item.sku_id, item.quantity) for item in env.cart.cart.items] == [("P2", "蓝", 1)]


async def test_confirmation_fails_if_status_changes_before_order_tool_reads(monkeypatch):
    from app.repositories.order_repo import MemOrderRepository
    from app.services.shop_action_confirmation import confirm_order_action, offer_order_confirmation

    repo = MemOrderRepository()
    repo.seed([{"order_id": "ORD-1", "user_id": "buyer", "status": "pending"}])
    read = repo.aget
    reads = 0

    async def aget(order_id, *, user_id):
        nonlocal reads
        reads += 1
        if reads == 3:
            assert await repo.aupdate_status(order_id, "paid", user_id=user_id, expected_status="pending")
        return await read(order_id, user_id=user_id)

    monkeypatch.setattr(repo, "aget", aget)
    monkeypatch.setattr("app.repositories.order_repo.get_order_repo", lambda: repo)
    offer = await offer_order_confirmation("buyer", "order.cancel", "ORD-1")
    result = await confirm_order_action("buyer", offer.actions[0]["confirmation"])
    assert not result.ok and "订单状态已变化" in result.message
    assert (await read("ORD-1", user_id="buyer"))["status"] == "paid"


async def test_cart_tools_use_memory_cart_repository(env, monkeypatch):
    from app.repositories.pg_cart_repo import MemCartRepository
    from app.providers.tools import get_tool_registry

    repo = MemCartRepository()
    monkeypatch.setattr("app.repositories.pg_cart_repo.get_cart_repo", lambda: repo)
    ctx = ToolContext(user_id="u1")
    registry = get_tool_registry()
    assert (await registry.invoke("cart.add", {"product_id": "P1"}, ctx)).ok
    item = (await repo.aget_cart("u1")).items[0]
    assert (await registry.invoke("cart.update_qty", {"cart_item_id": item.cart_item_id, "quantity": 3}, ctx)).ok
    assert item.quantity == 3
    assert (await registry.invoke("cart.remove", {"cart_item_id": item.cart_item_id}, ctx)).ok
    assert not (await repo.aget_cart("u1")).items


async def test_compound_cart_action_skips_duplicate_with_explicit_default(env, monkeypatch):
    from app.services.chat_shopping_intent import ShoppingIntent
    from app.services.chat_shopping_router import run_shopping_turn

    env.conv._snap["last_products"] = [{"product_id": "P1", "title": "Coffee"}]
    decisions = iter([
        ShoppingIntent(action="cart.add", product=["p1"], continue_after=True),
        ShoppingIntent(action="cart.add", product=["p1"], quantity=1, question="extra"),
    ])

    async def interpret(*_):
        return next(decisions)

    monkeypatch.setattr("app.services.chat_shopping_router.understand_shopping_turn", interpret)
    await run_shopping_turn(ToolContext(user_id="u1", conversation_id="cid1", args_raw="加一件再看购物车"),
                            env.conv, authenticated=True, payment_available=False)
    assert len(env.cart.cart.items) == 1 and env.cart.cart.items[0].quantity == 1
