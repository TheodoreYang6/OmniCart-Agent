"""Payment intent routing and explicit-confirmation gates."""

import pytest

from app.framework.tools import ToolContext
from app.providers.tools.cart_payment import CONFIRM, QUOTE, STATUS, cart_payment_tools, payment_intent


@pytest.mark.parametrize(("message", "expected"), [
    ("请帮我用支付宝结算购物车里的商品", QUOTE),
    ("好的，我确认使用支付宝支付这笔购物车订单", CONFIRM),
    ("查询支付结果", STATUS),
    ("我已经付款了", STATUS),
    ("不要给购物车付款", None),
    ("确认支付？", None),
    ("怎么在购物车支付", None),
    ("把这款商品加入购物车", None),
    # 确认语句不应被误判为报价
    ("确认支付购物车", CONFIRM),
    ("确认支付", CONFIRM),
    ("确认付款", CONFIRM),
    ("确认使用支付宝支付", CONFIRM),
    # 纯报价不含确认词
    ("结算购物车", QUOTE),
    ("购物车结算", QUOTE),
])
def test_payment_intent_is_explicit(message, expected):
    assert payment_intent(message) == expected


@pytest.mark.asyncio
async def test_payment_confirmation_requires_user_gate_and_stays_out_of_model_tools():
    tools = cart_payment_tools()
    assert tools.openai_schemas(llm_only=True) == []
    result = await tools.invoke(CONFIRM, {}, ToolContext(user_id="buyer", session_id="chat"))
    assert not result.ok
    assert result.error == "confirmation_required"
