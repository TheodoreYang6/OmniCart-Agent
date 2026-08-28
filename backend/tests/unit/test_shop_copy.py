"""购物动作文案与下单总结 prompt 的回归测试。"""

from app.prompts.api_prompts import build_order_summary_prompt
from app.services.shop_copy import cart_added, sku_picker


def test_cart_added_and_sku_picker_copy():
    assert "3 件" in cart_added("测试商品", "黑色", 3, 199.0)
    assert "3 个规格" in sku_picker("测试商品", 3)


def test_build_order_preview_prompt_contains_items_and_address():
    card = {
        "kind": "order_preview",
        "payload": {
            "items": [{"brand": "A", "title": "B", "price": 100, "quantity": 2}],
            "total": 200,
            "address": {"name": "张三", "phone": "138", "province": "浙江", "city": "杭州"},
            "has_address": True,
        },
    }
    prompt = build_order_summary_prompt(card)
    assert "A B" in prompt
    assert "¥200" in prompt
    assert "张三" in prompt


def test_build_order_created_prompt_contains_order_id():
    card = {
        "kind": "order_created",
        "payload": {
            "order_id": "ORD-ABCD1234",
            "items": [{"brand": "A", "title": "B", "price": 100, "quantity": 1}],
            "total": 100,
            "eta": "2-3天",
        },
    }
    prompt = build_order_summary_prompt(card)
    assert "ORD-ABCD1234" in prompt
    assert "2-3天" in prompt
