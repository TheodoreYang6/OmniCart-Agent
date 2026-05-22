"""Agent Actions API — 豆仔受控操作（加入购物车等）"""

import uuid
from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.cart import CartItem, CartItemCreate, DEMO_USER_ID
from app.repositories.product_repo import get_product_repo
from app.repositories.pg_cart_repo import get_cart_repo

router = APIRouter()


class AgentActionRequest(BaseModel):
    action: str  # add_to_cart / view_detail / compare / ...
    product_id: str
    user_id: str = DEMO_USER_ID
    session_id: str = ""


@router.post("/api/agent/action")
async def agent_action(req: AgentActionRequest):
    if req.action == "add_to_cart":
        repo = get_product_repo()
        product = repo.get_by_id(req.product_id)
        if not product:
            return {"error": "product not found"}

        cart_repo = get_cart_repo()
        cart_item = cart_repo.add_item(
            CartItemCreate(product_id=req.product_id, quantity=1),
            user_id=req.user_id,
            title=product.title,
            brand=product.brand,
            price=product.base_price,
            image_url=repo.resolve_image_url(product.product_id),
        )
        cart = cart_repo.get_cart(req.user_id)
        return {
            "status": "ok",
            "action": "add_to_cart",
            "product_title": product.title,
            "cart_item": cart_item.model_dump() if cart_item else None,
            "cart_count": len(cart.items),
        }

    return {"error": f"unknown action: {req.action}"}
