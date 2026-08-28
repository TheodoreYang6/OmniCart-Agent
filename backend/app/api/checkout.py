"""结算 API —— 预览 / 提交两步 + 订单列表。与聊天订单工具共用 checkout_service。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.identity import Actor, require_user, resolve_actor
from app.repositories.pg_cart_repo import get_cart_repo
from app.schemas.cart import CheckoutRequest
from app.services.checkout_service import (
    default_address,
    order_created_card,
    order_preview_card,
    order_total,
    enrich_order_items,
    persist_order,
    summarize_order,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _selected_items(cart, item_ids: list[str]):
    return [
        i for i in cart.items
        if i.selected and (not item_ids or i.cart_item_id in item_ids)
    ]


@router.post("/api/checkout/preview")
async def checkout_preview(req: CheckoutRequest = CheckoutRequest(), actor: Actor = Depends(resolve_actor)):
    actor = require_user(actor)
    cart = get_cart_repo().get_cart(actor.user_id)
    selected = _selected_items(cart, req.item_ids)
    if not selected:
        raise HTTPException(status_code=400, detail="请选择要结算的商品")
    items = [i.model_dump() for i in selected]
    address = await default_address(actor.user_id)
    shop_card, message, actions, total = order_preview_card(items, address)
    return {
        "shop_card": shop_card,
        "message": message,
        "actions": actions,
        "total": total,
        "has_address": bool(address),
    }


@router.post("/api/checkout/submit")
async def checkout_submit(req: CheckoutRequest = CheckoutRequest(), actor: Actor = Depends(resolve_actor)):
    actor = require_user(actor)
    cart = get_cart_repo().get_cart(actor.user_id)
    selected = _selected_items(cart, req.item_ids)
    if not selected:
        raise HTTPException(status_code=400, detail="请选择要结算的商品")
    address = await default_address(actor.user_id)
    if not address:
        raise HTTPException(status_code=422, detail="请先填写收货地址")

    items = [i.model_dump() for i in selected]
    total = order_total(items)
    try:
        order_id = await persist_order(actor.user_id, items, total)
    except Exception as exc:  # noqa: BLE001
        logger.error("checkout submit failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="订单提交失败，请稍后再试")

    get_cart_repo().batch_remove([i.cart_item_id for i in selected], actor.user_id)
    shop_card, message = order_created_card(order_id, items, total)
    answer = await summarize_order(shop_card, message)
    return {
        "shop_card": shop_card,
        "message": message,
        "answer": answer,
        "order_id": order_id,
        "total": total,
    }


@router.post("/api/checkout")
async def checkout(req: CheckoutRequest = CheckoutRequest(), actor: Actor = Depends(resolve_actor)):
    """兼容旧调用：直接提交结算（等价于 submit）。"""
    return await checkout_submit(req, actor)


@router.get("/api/orders")
async def list_orders(user_id: str = Query(default=""), actor: Actor = Depends(resolve_actor)):
    """获取用户订单列表。"""
    user_id = require_user(actor).user_id
    try:
        from app.core.database import get_session_sync
        from sqlalchemy import select
        from app.models.order import OrderModel

        factory = get_session_sync()
        if factory is None:
            raise RuntimeError("PostgreSQL 未配置")

        async with factory() as session:
            result = await session.execute(
                select(OrderModel)
                .where(OrderModel.user_id == user_id)
                .order_by(OrderModel.created_at.desc())
            )
            orders = [r.to_dict() for r in result.scalars().all()]
            # Historical orders may predate image_url / sku_label persistence.
            # Normalize only the nested display payload so the API is backward
            # compatible and every order item with a product id can render.
            for order in orders:
                order["items"] = enrich_order_items(order.get("items") or [])
        return {"user_id": user_id, "orders": orders, "count": len(orders)}
    except Exception as exc:  # noqa: BLE001
        logger.error("list_orders failed for %s: %s", user_id, exc, exc_info=True)
        return {"user_id": user_id, "orders": [], "count": 0, "error": "暂时无法获取订单列表"}
