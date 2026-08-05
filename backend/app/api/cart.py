"""购物车 API — V1 支持 PostgreSQL 持久化 + 内存降级。

通过 get_cart_repo() 自动选择存储后端：
- USE_POSTGRES=true  → PgCartRepository
- USE_POSTGRES=false → MemCartRepository（默认）
"""

import logging
from fastapi import APIRouter, Depends, Query

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
    user_id = actor_or_legacy(actor, user_id).user_id
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
                      actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id).user_id
    from app.repositories.product_repo import get_product_repo
    repo = get_product_repo()
    product = repo.get_by_id(item.product_id)
    if not product:
        return {"error": "product not found"}
    # P0: SKU 归属校验
    if item.sku_id:
        valid_sku = any(s.sku_id == item.sku_id for s in (product.skus or []))
        if not valid_sku:
            return {"error": "sku not found for this product"}

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
    cart_item = cart_repo.add_item(
        item, user_id,
        title=product.title,
        brand=product.brand,
        price=sku_price,
        image_url=repo.resolve_image_url(product.product_id),
        sku_label=sku_label,
    )
    if cart_item is None:
        return {"error": "failed to add item"}

    return cart_item.model_dump()


@router.put("/api/cart/items/{cart_item_id}")
async def update_cart_item(cart_item_id: str, update: CartItemUpdate, user_id: str = DEMO_USER_ID,
                            session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                            actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id).user_id
    cart_repo = get_cart_repo()
    item = cart_repo.update_item(cart_item_id, update, user_id)
    if item is None:
        return {"error": "item not found"}
    return item.model_dump()


@router.delete("/api/cart/items/{cart_item_id}")
async def remove_cart_item(cart_item_id: str, user_id: str = DEMO_USER_ID,
                           session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                           actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id).user_id
    cart_repo = get_cart_repo()
    ok = cart_repo.remove_item(cart_item_id, user_id)
    return {"ok": ok}


@router.post("/api/cart/select-all")
async def select_all(selected: bool = True, user_id: str = DEMO_USER_ID,
                     session_id: str = Query(default=""), conversation_id: str = Query(default=""),
                     actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id).user_id
    cart_repo = get_cart_repo()
    cart_repo.select_all(selected, user_id)
    return {"ok": True, "selected": selected}


@router.delete("/api/cart/clear")
async def clear_cart(user_id: str = DEMO_USER_ID,
                     session_id: str = Query(default=""),
                     conversation_id: str = Query(default=""),
                     actor: Actor = Depends(resolve_actor)):
    user_id = actor_or_legacy(actor, user_id).user_id
    cart_repo = get_cart_repo()
    cart_repo.clear_cart(user_id)
    return {"ok": True, "session_id": session_id, "conversation_id": conversation_id}
