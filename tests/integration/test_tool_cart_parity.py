"""购物车工具 A/B 对拍 — 工具路径产出的文案/终态与旧实现等价。

用内存异步 fake cart repo（无需 PostgreSQL），monkeypatch get_cart_repo。
验证 ShopActionAgent → ToolDispatcher → 购物车工具 全链路。
"""

import pytest

from app.framework.tools import ToolContext
from app.schemas.cart import Cart, CartItem, CartItemUpdate


class _FakeAsyncCartRepo:
    """最小内存异步购物车仓库（复刻 pg_cart_repo 的 async 方法语义）。"""

    def __init__(self, items=None):
        self.cart = Cart(user_id="u1", items=items or [])

    async def aget_cart(self, user_id="u1"):
        return self.cart

    async def aremove_item(self, cart_item_id, user_id="u1"):
        before = len(self.cart.items)
        self.cart.items = [i for i in self.cart.items if i.cart_item_id != cart_item_id]
        return len(self.cart.items) < before

    async def aupdate_item(self, cart_item_id, update_data: CartItemUpdate, user_id="u1"):
        for it in self.cart.items:
            if it.cart_item_id == cart_item_id:
                if update_data.quantity is not None:
                    it.quantity = max(1, update_data.quantity)
                return it
        return None

    async def aclear_cart(self, user_id="u1"):
        self.cart.items = []
        return True


def _items():
    return [
        CartItem(cart_item_id="a1", product_id="P1", title="降噪耳机", brand="Sony", price=1200, quantity=1),
        CartItem(cart_item_id="a2", product_id="P2", title="速溶咖啡", brand="雀巢", price=99, quantity=2),
        CartItem(cart_item_id="a3", product_id="P3", title="跑步鞋", brand="Nike", price=599, quantity=1),
    ]


@pytest.fixture
def fake_repo(monkeypatch):
    repo = _FakeAsyncCartRepo(_items())
    monkeypatch.setattr("app.repositories.pg_cart_repo.get_cart_repo", lambda: repo)
    return repo


async def _handle(msg: str):
    from app.agents.shop_action_agent import ShopActionAgent

    ctx = ToolContext(user_id="u1", args_raw=msg)
    res = await ShopActionAgent().handle(msg, ctx)
    return res, ctx


async def test_view(fake_repo):
    res, ctx = await _handle("看看购物车")
    assert res.ok and "购物车" in res.message
    assert res.data["shop_card"]["kind"] == "cart_summary"
    assert res.data["shop_card"]["payload"]["count"] == 4
    assert res.data["shop_card"]["payload"]["total"] == 1997
    assert ctx.tool_trace[0]["skill_name"] == "cart.view"


async def test_remove_ordinal(fake_repo):
    res, _ = await _handle("删除第二个")
    assert "已删除" in res.message and "雀巢" in res.message
    assert [i.cart_item_id for i in fake_repo.cart.items] == ["a1", "a3"]


async def test_remove_out_of_range(fake_repo):
    res, _ = await _handle("删除第九个")
    assert not res.ok and "只有3件" in res.message
    assert len(fake_repo.cart.items) == 3


async def test_update_qty_default_first(fake_repo):
    res, _ = await _handle("数量改成3")
    assert "数量已改为 3" in res.message
    assert fake_repo.cart.items[0].quantity == 3


async def test_clear(fake_repo):
    res, _ = await _handle("清空购物车")
    assert "已清空" in res.message
    assert fake_repo.cart.items == []


async def test_unmatched_falls_to_prompt(fake_repo):
    # Phase 2: ShopActionAgent 接管全部购物动作；未匹配任何动作 → 兜底提示（不再 no_match）
    res, _ = await _handle("你觉得呢")
    assert res.ok and "问欧米" in res.message
