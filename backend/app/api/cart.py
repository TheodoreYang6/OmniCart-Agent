"""购物车 API — V1 支持 PostgreSQL 持久化 + 内存降级。

通过 get_cart_repo() 自动选择存储后端：
- USE_POSTGRES=true  → PgCartRepository
- USE_POSTGRES=false → MemCartRepository（默认）
"""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.cart import CartItemCreate, CartItemUpdate, DEMO_USER_ID
from app.repositories.pg_cart_repo import get_cart_repo
from app.core.identity import Actor, actor_or_legacy, resolve_actor

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/cart")
async def get_cart(user_id: str = DEMO_USER_ID,
                   session_id: str = Query(default=""),
                   conversation_id: str = Query(default=""),
                   actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id, protected=True).user_id
    repo = get_cart_repo()
    cart = repo.get_cart(user_id)
    return {
        "user_id": cart.user_id,
        "session_id": session_id,
        "conversation_id": conversation_id,
        "items": [item.model_dump() for item in cart.items],
        "total_price": cart.total_price,
        "total_count": cart.total_count,
    }


@router.post("/api/cart/items")
async def add_to_cart(item: CartItemCreate, user_id: str = DEMO_USER_ID,
                      session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                      actor: Actor = Depends(resolve_actor),
                      selection_id: Annotated[str | None, Query(pattern=r"^(?:[a-f0-9]{32}|legacy)$")] = None):
    user_id = actor_or_legacy(actor, user_id, protected=True).user_id
    if selection_id and not conversation_id:
        raise HTTPException(422, "缺少选择规格的会话。")
    from app.repositories.product_repo import get_product_repo
    repo = get_product_repo()
    product = repo.get_by_id(item.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    # P0: SKU 归属校验
    if item.sku_id:
        valid_sku = any(s.sku_id == item.sku_id for s in (product.skus or []))
        if not valid_sku:
            raise HTTPException(status_code=422, detail="sku not found for this product")

    # 构建 sku_label + 取 SKU 价格
    sku_label = ""
    sku_price = product.base_price
    if item.sku_id:
        for sku in (product.skus or []):
            if sku.sku_id == item.sku_id:
                sku_label = " · ".join(f"{k}:{v}" for k, v in (sku.properties or {}).items())
                sku_price = sku.price if sku.price > 0 else product.base_price
                break

    cart_repo = get_cart_repo()
    details = {
        "title": product.title, "brand": product.brand, "price": sku_price,
        "image_url": repo.resolve_image_url(product.product_id), "sku_label": sku_label,
    }
    if selection_id:
        pending_id = "" if selection_id == "legacy" else selection_id
        cart_item = await cart_repo.aadd_item(item, user_id, pending_sku=(conversation_id, pending_id), **details)
        if cart_item is None:
            raise HTTPException(409, "这张规格卡已处理或已更新，请重新发起加购。")
    else:
        cart_item = cart_repo.add_item(item, user_id, **details)
        if cart_item is None:
            raise HTTPException(status_code=500, detail="failed to add item")

    if conversation_id:
        try:
            from app.services.conversation_service import get_conversation_service

            conv = get_conversation_service()
            if selection_id:
                conv.invalidate_context_snapshot(conversation_id, user_id=user_id)
            else:
                snapshot = await conv.get_context_snapshot(conversation_id, user_id=user_id)
                pending = snapshot.get("pending_sku_product") or {}
                if not pending.get("selection_id") and pending.get("product_id") == item.product_id:
                    await conv.aupdate_context_snapshot(conversation_id, {"pending_sku_product": None}, user_id=user_id)
        except Exception:
            logger.debug("Could not clear completed cart SKU selection")

    return cart_item.model_dump()


@router.put("/api/cart/items/{cart_item_id}")
async def update_cart_item(cart_item_id: str, update: CartItemUpdate, user_id: str = DEMO_USER_ID,
                            session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                            actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id, protected=True).user_id
    cart_repo = get_cart_repo()
    item = cart_repo.update_item(cart_item_id, update, user_id)
    if item is None:
        return {"error": "item not found"}
    return item.model_dump()


@router.delete("/api/cart/items/{cart_item_id}")
async def remove_cart_item(cart_item_id: str, user_id: str = DEMO_USER_ID,
                           session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                           actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id, protected=True).user_id
    cart_repo = get_cart_repo()
    ok = cart_repo.remove_item(cart_item_id, user_id)
    return {"ok": ok}


@router.post("/api/cart/select-all")
async def select_all(selected: bool = True, user_id: str = DEMO_USER_ID,
                     session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                     actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id, protected=True).user_id
    cart_repo = get_cart_repo()
    cart_repo.select_all(selected, user_id)
    return {"ok": True, "selected": selected}


@router.delete("/api/cart/clear")
async def clear_cart(user_id: str = DEMO_USER_ID,
                     session_id: str = Query(default=""),
                     conversation_id: str = Query(default=""),
                     actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id, protected=True).user_id
    cart_repo = get_cart_repo()
    cart_repo.clear_cart(user_id)
    return {"ok": True, "session_id": session_id, "conversation_id": conversation_id}
