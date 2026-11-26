"""User-click confirmation for simulation-only actions on existing orders."""

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException

from app.core.config import settings
from app.framework.tools import ToolContext, ToolResult

_LABELS = {"order.cancel": "确认取消订单", "order.pay": "确认模拟付款"}


def _sign(body: bytes) -> str:
    return hmac.new(settings.session_secret.encode(), b"shop-confirmation:" + body, hashlib.sha256).hexdigest()


async def _owned_simulated_order(user_id: str, order_id: str) -> dict:
    from app.repositories.order_repo import get_order_repo

    order = await get_order_repo().aget(order_id, user_id=user_id)
    if not order:
        raise HTTPException(404, "没有找到这笔订单。")
    if order.get("payment_environment"):
        raise HTTPException(409, "这笔订单关联了支付宝，请在对应支付页面处理。")
    return order


async def offer_order_confirmation(user_id: str, action: str, order_id: str) -> ToolResult:
    try:
        order = await _owned_simulated_order(user_id, order_id)
    except HTTPException as exc:
        return ToolResult(ok=False, message=str(exc.detail))
    body = base64.urlsafe_b64encode(json.dumps(
        [user_id, action, order_id, order.get("status"), int(time.time()) + 300],
        separators=(",", ":"),
    ).encode())
    label = _LABELS[action]
    return ToolResult(
        message=f"请核对订单 {order_id}，再点「{label}」。",
        actions=[{"type": "confirm_shop_action", "label": label, "confirmation": body.decode() + "." + _sign(body)}],
    )


async def confirm_order_action(user_id: str, token: str) -> ToolResult:
    from app.providers.tools import get_tool_registry

    try:
        encoded, signature = token.split(".", 1)
        body = encoded.encode("ascii")
        if not hmac.compare_digest(signature, _sign(body)):
            raise ValueError
        owner, action, order_id, original_status, expires = json.loads(base64.urlsafe_b64decode(body))
        if owner != user_id or action not in _LABELS or expires < time.time():
            raise ValueError
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(400, "确认操作已失效，请在聊天中重新发起。") from None
    order = await _owned_simulated_order(user_id, order_id)
    if order.get("status") != original_status:
        raise HTTPException(409, "订单状态已变化，请重新核对。")
    return await get_tool_registry().invoke(
        action, {"order_id": order_id, "expected_status": original_status, "_confirmed": True},
        ToolContext(user_id=user_id),
    )
