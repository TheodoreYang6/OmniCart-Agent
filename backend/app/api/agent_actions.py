"""Agent Actions API — 欧米受控操作（加入购物车等）"""

import uuid
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.schemas.cart import CartItem, CartItemCreate, DEMO_USER_ID
from app.repositories.product_repo import get_product_repo
from app.repositories.pg_cart_repo import get_cart_repo
from app.core.identity import Actor, resolve_actor

logger = logging.getLogger(__name__)
router = APIRouter()


class AgentActionRequest(BaseModel):
    action: str  # add_to_cart / view_detail / compare / ...
    product_id: str
    user_id: str = DEMO_USER_ID
    session_id: str = ""
    conversation_id: str = ""


@router.post("/api/agent/action")
async def agent_action(req: AgentActionRequest, actor: Actor = Depends(resolve_actor)):
    if isinstance(actor, Actor):
        req.user_id = actor.user_id
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
            sku_label="",  # agent action 不加 SKU（无用户选择）
        )
        cart = cart_repo.get_cart(req.user_id)

        # F7-3: 加购 trace — 写入 conversation context_snapshot
        if req.conversation_id:
            try:
                from app.services.conversation_service import get_conversation_service
                conv_svc = get_conversation_service()
                await conv_svc.aupdate_context_snapshot(req.conversation_id, {
                    "last_action": "add_to_cart",
                    "last_added_product_id": req.product_id,
                    "last_added_product_title": product.title,
                })
            except Exception as e:
                logger.debug(f"Context snapshot skipped: {e}")

        return {
            "status": "ok",
            "action": "add_to_cart",
            "product_title": product.title,
            "cart_item": cart_item.model_dump() if cart_item else None,
            "cart_count": len(cart.items),
        }

    return {"error": f"unknown action: {req.action}"}
