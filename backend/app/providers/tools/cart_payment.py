"""Cart payment tools reserved for explicit requests in the chat transport."""

from functools import lru_cache
import re

from fastapi import HTTPException

from app.core.database import get_session_sync
from app.framework.tools import Tool, ToolContext, ToolRegistry, ToolResult, ToolSpec
from app.services.checkout_payment import chat_cart_payment, confirm_cart, quote_cart
from app.services.checkout_service import order_preview_card
from app.services.payment_settlement import _expired, _refresh, fulfillment_status

QUOTE = "order.cart_payment_quote"
CONFIRM = "order.cart_payment_confirm"
STATUS = "order.cart_payment_status"
OPEN = "order.cart_payment_open"

_SETTLED_MESSAGES = {
    "paid": "已确认付款成功，购物订单已保存。",
    "partially_refunded": "支付宝已确认这笔订单部分退款。",
    "refunded": "支付宝已确认这笔订单全额退款。",
}


def payment_intent(message: str) -> str | None:
    text = re.sub(r"[\s，,。！!]+", "", message)
    if re.fullmatch(r"(?:好[的呀]?|是的)?(?:我)?确认(?:使用|用)?(?:支付宝)?(?:支付|付款)(?:(?:这笔)?(?:购物车)?(?:订单)?)?(?:吧)?", text):
        return CONFIRM
    if re.fullmatch(r"(?:帮我)?(?:查(?:询|看)?(?:一下)?(?:支付|付款)(?:结果|状态)|我(?:已经)?(?:付完了|付款了|支付了)|支付成功了吗)[？?]?", text):
        return STATUS
    # CONFIRM 已在上面精确匹配；此处只需检测报价意图。
    # 排除"确认"前缀避免把"确认支付购物车"这类已确认语句降级为报价。
    if ("购物车" in text and re.search(r"结算|支付|付款|买单", text)
            and not re.search(r"不要|别|取消|先不|不想|还不|怎么|如何|能否|能不能|失败|确认", text)):
        return QUOTE
    return None


def _factory(ctx: ToolContext):
    factory = get_session_sync()
    if not factory or not ctx.user_id:
        raise HTTPException(503, "购物车支付服务暂不可用")
    if not ctx.session_id or len(ctx.session_id) > 64:
        raise HTTPException(422, "请打开当前对话后重新发起结算")
    return factory


def _route(order) -> str:
    return f"cart?payment={order.order_id}"


def _view_action(order, label="查看购物车支付") -> dict:
    return {"type": "quick_reply", "label": label, "route": _route(order)}


class CartPaymentQuote(Tool):
    spec = ToolSpec(name=QUOTE, category="order", permission="write", llm_exposed=False,
                    description="为当前购物车选中商品生成支付报价")

    async def run(self, ctx: ToolContext) -> ToolResult:
        try:
            async with _factory(ctx)() as session:
                order = await quote_cart(session, ctx.user_id, [], ctx.session_id)
        except HTTPException as exc:
            actions = [{"type": "address_form", "label": "填写收货地址"}] if exc.status_code == 422 else []
            return ToolResult(ok=False, message=str(exc.detail), actions=actions)
        status = fulfillment_status(order)
        if status in _SETTLED_MESSAGES:
            return ToolResult(message=_SETTLED_MESSAGES[status], actions=[_view_action(order, "查看付款结果")])

        address = {**order.report["address"]}
        if address.get("phone"):
            address["phone"] = "****" + address["phone"][-4:]
        card, _, _, _ = order_preview_card(order.report["items"], address)
        total = f"{order.amount_fen / 100:.2f}"
        if order.chat_session_id != ctx.session_id:
            message = f"你已有一笔待支付的购物车订单，应付 ¥{total}。请先打开这笔订单查看。"
        elif order.status == "pending":
            message = f"这笔 ¥{total} 的订单已确认。你可以打开购物车查看支付状态。"
        else:
            message = f"购物车选中商品应付 ¥{total}。请打开支付预览核对商品和地址，再确认。"
        return ToolResult(message=message, data={"shop_card": card}, actions=[_view_action(order, "打开支付预览")])


class CartPaymentConfirm(Tool):
    spec = ToolSpec(name=CONFIRM, category="order", permission="order", llm_exposed=False,
                    description="在用户明确确认后打开当前对话订单的支付宝收银台")

    async def run(self, ctx: ToolContext) -> ToolResult:
        try:
            async with _factory(ctx)() as session:
                order = await chat_cart_payment(session, ctx.user_id, ctx.session_id)
                order, url = await confirm_cart(session, ctx.user_id, order.order_id)
        except HTTPException as exc:
            return ToolResult(ok=False, message=str(exc.detail))
        status = fulfillment_status(order)
        if status in _SETTLED_MESSAGES:
            return ToolResult(message=_SETTLED_MESSAGES[status], actions=[_view_action(order, "查看付款结果")])
        if url:
            action = {"type": "cart_payment_handoff", "label": "前往支付宝付款", "checkout_url": url}
            return ToolResult(message="已打开这笔订单的支付宝支付入口，请在支付宝完成付款。",
                              actions=[action, _view_action(order, "查看付款结果")])
        return ToolResult(message="演示订单已确认。打开购物车支付页可模拟付款。",
                          actions=[_view_action(order, "打开演示收银台")])


class CartPaymentOpen(Tool):
    spec = ToolSpec(name=OPEN, category="order", llm_exposed=False,
                    description="打开当前对话的购物车支付确认页")

    async def run(self, ctx: ToolContext) -> ToolResult:
        try:
            async with _factory(ctx)() as session:
                order = await chat_cart_payment(session, ctx.user_id, ctx.session_id)
        except HTTPException as exc:
            return ToolResult(ok=False, message=str(exc.detail))
        return ToolResult(message="请在支付页核对商品和金额后确认。",
                          actions=[_view_action(order, "打开支付确认页")])


class CartPaymentStatus(Tool):
    spec = ToolSpec(name=STATUS, category="order", llm_exposed=False, timeout_ms=12000,
                    description="读取并核验当前对话中的购物车付款结果")

    async def run(self, ctx: ToolContext) -> ToolResult:
        try:
            async with _factory(ctx)() as session:
                order = await chat_cart_payment(session, ctx.user_id, ctx.session_id)
                order = await _refresh(session, order.order_id, ctx.user_id, "cart")
        except HTTPException as exc:
            return ToolResult(ok=False, message=str(exc.detail))
        messages = {
            **_SETTLED_MESSAGES,
            "quoted": "购物车订单等待确认，请打开支付页核对后确认。",
            "pending": "这笔订单还在等待支付宝确认，请查看支付状态。",
            "closed": "这笔支付订单已关闭，可以重新发起购物车结算。",
        }
        message = messages[fulfillment_status(order)]
        if order.status == "pending" and _expired(order):
            message = "这笔订单的支付链接已过期，请查询支付宝账单并核对订单状态。"
        return ToolResult(message=message, actions=[_view_action(order, "查看付款结果")])


@lru_cache(maxsize=1)
def cart_payment_tools() -> ToolRegistry:
    registry = ToolRegistry(kind="tool")
    registry.register_all([CartPaymentQuote(), CartPaymentConfirm(), CartPaymentOpen(), CartPaymentStatus()])
    return registry
