"""统一的订单预览 / 提交 / 收尾逻辑，供聊天工具与 REST 结算共用。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.prompts.api_prompts import build_order_summary_prompt

logger = logging.getLogger(__name__)

_ETA = "2-3天"


def normalize_items(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        price = float(it.get("price") or 0)
        qty = int(it.get("quantity") or 1)
        out.append({
            "product_id": str(it.get("product_id", "")),
            "cart_item_id": str(it.get("cart_item_id", "")),
            "title": str(it.get("title", "")),
            "brand": str(it.get("brand", "")),
            "price": price,
            "quantity": qty,
            "image_url": str(it.get("image_url", "") or ""),
            "sku_id": str(it.get("sku_id", "") or "") or None,
            "sku_label": str(it.get("sku_label", "") or ""),
        })
    return out


def enrich_order_items(items: list[dict]) -> list[dict]:
    """Keep old orders displayable even when their historical payload missed an image.

    Cart and new checkout payloads already contain a concrete image URL.  For an
    order made by an older chat/tool flow we have a stable product id, so the
    product-image endpoint is a safe, version-independent fallback.  We do not
    guess an image from a title when the id itself is absent.
    """
    normalized = normalize_items(items)
    for item in normalized:
        if not item["image_url"] and item["product_id"]:
            item["image_url"] = f"/api/products/{item['product_id']}/image"
    return normalized


def order_total(items: list[dict]) -> float:
    total = sum(
        (Decimal(str(it.get("price") or 0)) * int(it.get("quantity") or 1) for it in items),
        Decimal("0"),
    )
    return float(total.quantize(Decimal("0.01")))


def order_preview_card(items: list[dict], address: dict | None) -> tuple[dict, str, list[dict], float]:
    normalized = enrich_order_items(items)
    total = order_total(normalized)
    shop_card = {
        "kind": "order_preview",
        "payload": {
            "items": normalized,
            "total": total,
            "address": address,
            "has_address": bool(address),
        },
    }
    if address:
        message = f"帮你整理好了，一共 {len(normalized)} 件，合计 ¥{total:.0f}。确认没问题就下单，地址不对可以改。"
        actions = [
            {"type": "quick_reply", "label": "确认下单"},
            {"type": "address_form", "label": "修改地址"},
        ]
    else:
        message = f"帮你整理好了，一共 {len(normalized)} 件，合计 ¥{total:.0f}。还差一个收货地址，先填一下。"
        actions = [{"type": "address_form", "label": "填写收货地址"}]
    return shop_card, message, actions, total


def order_created_card(order_id: str, items: list[dict], total: float) -> tuple[dict, str]:
    normalized = enrich_order_items(items)
    shop_card = {
        "kind": "order_created",
        "payload": {
            "order_id": order_id,
            "items": normalized,
            "total": total,
            "eta": _ETA,
        },
    }
    message = f"下单成功，订单号 {order_id}，共 {len(normalized)} 件，合计 ¥{total:.0f}，预计 {_ETA}。"
    return shop_card, message


async def persist_order(user_id: str, items: list[dict], total: float) -> str:
    """持久化订单；任何失败都抛异常，绝不静默返回成功。"""
    normalized = enrich_order_items(items)
    if not normalized:
        raise ValueError("没有要结算的商品")
    from app.core.database import get_session_sync
    from app.models.order import OrderModel

    factory = get_session_sync()
    if factory is None:
        raise RuntimeError("PostgreSQL 未配置，无法提交订单")
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    async with factory() as session:
        order = OrderModel(
            order_id=order_id,
            user_id=user_id,
            items=normalized,
            total_price=total,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add(order)
        await session.commit()
    return order_id


async def summarize_order(shop_card: dict, fallback_message: str) -> str:
    """用接地 prompt 生成 LLM 收尾；失败回退确定性文案。"""
    try:
        from app.model_gateway.gateway import get_model_gateway

        prompt = build_order_summary_prompt(shop_card)
        text = ""
        async for token in get_model_gateway().chat_stream("chat_generation", prompt):
            text += token
        text = text.strip()
        if text:
            return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("order summary LLM failed, using template: %s", exc)
    return fallback_message


async def default_address(user_id: str) -> dict | None:
    if not user_id:
        return None
    from app.repositories.address_repo import get_address_repo

    repo = get_address_repo()
    if hasattr(repo, "_alist"):
        addrs = await repo._alist(user_id)
    else:
        addrs = repo.list(user_id)
    return next((a for a in addrs if a.get("is_default")), addrs[0] if addrs else None)
