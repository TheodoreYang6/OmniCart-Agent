"""购物车 API — V1 支持 PostgreSQL 持久化 + 内存降级。

通过 get_cart_repo() 自动选择存储后端：
- USE_POSTGRES=true  → PgCartRepository
- USE_POSTGRES=false → MemCartRepository（默认）
"""

from fastapi import APIRouter

from app.schemas.cart import CartItemCreate, CartItemUpdate, DEMO_USER_ID
from app.repositories.pg_cart_repo import get_cart_repo

router = APIRouter()

# 向后兼容导出（checkout/agent_actions 直接引用此模块的 _get_cart）
def _get_cart(user_id: str = DEMO_USER_ID):
    return get_cart_repo().get_cart(user_id)


@router.get("/api/cart")
async def get_cart(user_id: str = DEMO_USER_ID):
    repo = get_cart_repo()
    cart = repo.get_cart(user_id)
    return {
        "user_id": cart.user_id,
        "items": [item.model_dump() for item in cart.items],
        "total_price": cart.total_price,
        "total_count": cart.total_count,
    }


@router.post("/api/cart/items")
async def add_to_cart(item: CartItemCreate, user_id: str = DEMO_USER_ID):
    from app.repositories.product_repo import get_product_repo
    repo = get_product_repo()
    product = repo.get_by_id(item.product_id)
    if not product:
        return {"error": "product not found"}

    cart_repo = get_cart_repo()
    cart_item = cart_repo.add_item(
        item, user_id,
        title=product.title,
        brand=product.brand,
        price=product.base_price,
        image_url=repo.resolve_image_url(product.product_id),
    )
    if cart_item is None:
        return {"error": "failed to add item"}
    return cart_item.model_dump()


@router.put("/api/cart/items/{cart_item_id}")
async def update_cart_item(cart_item_id: str, update: CartItemUpdate, user_id: str = DEMO_USER_ID):
    cart_repo = get_cart_repo()
    item = cart_repo.update_item(cart_item_id, update, user_id)
    if item is None:
        return {"error": "item not found"}
    return item.model_dump()


@router.delete("/api/cart/items/{cart_item_id}")
async def remove_cart_item(cart_item_id: str, user_id: str = DEMO_USER_ID):
    cart_repo = get_cart_repo()
    ok = cart_repo.remove_item(cart_item_id, user_id)
    return {"ok": ok}


@router.post("/api/cart/select-all")
async def select_all(selected: bool = True, user_id: str = DEMO_USER_ID):
    cart_repo = get_cart_repo()
    cart_repo.select_all(selected, user_id)
    return {"ok": True, "selected": selected}


@router.delete("/api/cart/clear")
async def clear_cart(user_id: str = DEMO_USER_ID):
    cart_repo = get_cart_repo()
    cart_repo.clear_cart(user_id)
    return {"ok": True}
