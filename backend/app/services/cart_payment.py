"""Price and fulfill a cart snapshot within the payment transaction."""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.address import AddressModel
from app.models.cart_item import CartItemModel
from app.models.order import OrderModel
from app.models.product import ProductModel
from app.models.report_order import ReportOrderModel
from app.models.user import UserModel
from app.services.checkout_service import enrich_order_items


async def lock_buyer(session: AsyncSession, user_id: str) -> None:
    await session.scalar(select(UserModel.user_id).where(UserModel.user_id == user_id).with_for_update())


async def snapshot_cart(session: AsyncSession, user_id: str, item_ids: list[str]) -> tuple[dict, int]:
    statement = (
        select(CartItemModel, ProductModel)
        .outerjoin(ProductModel, ProductModel.product_id == CartItemModel.product_id)
        .where(CartItemModel.user_id == user_id, CartItemModel.selected.is_(True))
        .order_by(CartItemModel.cart_item_id)
    )
    if item_ids:
        statement = statement.where(CartItemModel.cart_item_id.in_(item_ids))
    rows = (await session.execute(statement)).all()
    if not rows or (item_ids and len(rows) != len(set(item_ids))):
        raise HTTPException(409, "请重新选择要结算的商品")

    address = await session.scalar(
        select(AddressModel).where(AddressModel.user_id == user_id)
        .order_by(AddressModel.is_default.desc(), AddressModel.created_at, AddressModel.address_id).limit(1)
    )
    if address is None:
        raise HTTPException(422, "请先填写收货地址")

    total = Decimal(0)
    items = []
    item_versions = {}
    for item, product in rows:
        if product is None or item.quantity < 1:
            raise HTTPException(409, "购物车商品已变更，请重新选择")
        sku_price = None
        if item.sku_id:
            sku = next((entry for entry in (product.skus or []) if entry.get("sku_id") == item.sku_id), None)
            if sku is None:
                raise HTTPException(409, "商品规格已变更，请重新选择")
            sku_price = Decimal(str(sku.get("price") or 0))
        price = sku_price if sku_price and sku_price > 0 else Decimal(str(product.base_price))
        price = price.quantize(Decimal("0.01"))
        if price <= 0:
            raise HTTPException(409, "商品价格无效，请重新选择")
        total += price * item.quantity
        items.append({
            "cart_item_id": item.cart_item_id, "product_id": product.product_id, "sku_id": item.sku_id,
            "sku_label": item.sku_label, "title": product.title, "brand": product.brand,
            "price": float(price), "quantity": item.quantity, "image_url": item.image_url,
        })
        item_versions[item.cart_item_id] = item.updated_at.isoformat() if item.updated_at else None
    if total > Decimal("100000000"):
        raise HTTPException(422, "订单金额超出收银台上限")
    return {
        "items": enrich_order_items(items),
        "item_versions": item_versions,
        "address": {
            field: getattr(address, field)
            for field in ("address_id", "name", "phone", "province", "city", "district", "detail")
        },
    }, int(total * 100)


async def fulfill_cart(session: AsyncSession, payment: ReportOrderModel) -> None:
    """Create the paid order and remove only the unchanged rows that were paid for."""
    snapshot = payment.report
    session.add(OrderModel(
        order_id=payment.order_id, user_id=payment.user_id, items=snapshot["items"],
        shipping_address=snapshot["address"], total_price=payment.amount_fen / 100,
        status="paid", created_at=payment.paid_at or datetime.now(timezone.utc),
    ))
    for cart_id, version in snapshot["item_versions"].items():
        previous = datetime.fromisoformat(version) if version else None
        await session.execute(delete(CartItemModel).where(
            CartItemModel.user_id == payment.user_id, CartItemModel.cart_item_id == cart_id,
            CartItemModel.updated_at == previous,
        ))
