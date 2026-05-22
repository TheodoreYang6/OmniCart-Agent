"""Mock Checkout API — 模拟结算，不执行真实支付"""

import uuid
from fastapi import APIRouter

from app.schemas.cart import CheckoutRequest, CheckoutResponse, DEMO_USER_ID
from app.repositories.pg_cart_repo import get_cart_repo

router = APIRouter()


@router.post("/api/checkout")
async def checkout(req: CheckoutRequest = CheckoutRequest()):
    cart_repo = get_cart_repo()
    cart = cart_repo.get_cart(req.user_id or DEMO_USER_ID)
    selected = [i for i in cart.items if i.selected and (not req.item_ids or i.cart_item_id in req.item_ids)]

    if not selected:
        return {"error": "请选择要结算的商品"}

    total = sum(i.price * i.quantity for i in selected)
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    # 结算后从购物车移除
    for i in selected:
        cart_repo.remove_item(i.cart_item_id, req.user_id or DEMO_USER_ID)

    return CheckoutResponse(
        order_id=order_id,
        user_id=req.user_id or DEMO_USER_ID,
        items=selected,
        total_price=total,
        status="pending",
        message=f"模拟结算成功！订单号 {order_id}，共 {len(selected)} 件商品，合计 ¥{total:.2f}（未执行真实支付）",
    ).model_dump()
