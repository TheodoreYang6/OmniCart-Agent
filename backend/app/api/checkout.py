"""Mock Checkout API — 模拟结算 + 订单列表"""

import uuid
import logging
from fastapi import APIRouter, Query

from app.schemas.cart import CheckoutRequest, CheckoutResponse, DEMO_USER_ID
from app.repositories.pg_cart_repo import get_cart_repo

logger = logging.getLogger(__name__)
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

    # 持久化订单
    try:
        from app.core.database import get_session_sync, run_async
        from app.models.order import OrderModel
        from datetime import datetime, timezone

        async def _save_order():
            factory = get_session_sync()
            async with factory() as session:
                order = OrderModel(
                    order_id=order_id,
                    user_id=req.user_id or DEMO_USER_ID,
                    items=[i.model_dump() for i in selected],
                    total_price=total,
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                )
                session.add(order)
                await session.commit()
        await _save_order()
    except Exception as e:
        logger.warning(f"Order persist failed: {e}")

    # 结算后从购物车移除
    cart_repo.batch_remove([i.cart_item_id for i in selected], req.user_id or DEMO_USER_ID)

    return CheckoutResponse(
        order_id=order_id,
        user_id=req.user_id or DEMO_USER_ID,
        items=selected,
        total_price=total,
        status="pending",
        message=f"模拟结算成功！订单号 {order_id}，共 {len(selected)} 件商品，合计 ¥{total:.2f}（未执行真实支付）",
    ).model_dump()


@router.get("/api/orders")
async def list_orders(user_id: str = Query(default="")):
    """获取用户订单列表"""
    if not user_id:
        return {"orders": [], "count": 0}

    try:
        from app.core.database import get_session_sync
        from sqlalchemy import select, text
        from app.models.order import OrderModel

        async def _list():
            factory = get_session_sync()
            async with factory() as session:
                result = await session.execute(
                    select(OrderModel)
                    .where(OrderModel.user_id == user_id)
                    .order_by(OrderModel.created_at.desc())
                )
                return [r.to_dict() for r in result.scalars().all()]

        orders = await _list()
        return {"user_id": user_id, "orders": orders, "count": len(orders)}
    except Exception:
        return {"user_id": user_id, "orders": [], "count": 0}
