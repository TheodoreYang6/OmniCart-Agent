"""Create and confirm an authoritative cart payment quote."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.report_order import ReportOrderModel
from app.services.cart_payment import lock_buyer, snapshot_cart
from app.services.payment_settlement import _check_provider, _expired, _order, _provider, _refresh


def cart_provider():
    if settings.report_payment_mode == "production" and not settings.cart_allow_live_payment:
        raise HTTPException(503, "购物车正式收款尚未开通")
    return _provider()


async def pending_cart_payment(session: AsyncSession, user_id: str, *, lock: bool = False):
    statement = select(ReportOrderModel).where(
        ReportOrderModel.kind == "cart", ReportOrderModel.user_id == user_id,
        ReportOrderModel.status == "pending", ReportOrderModel.cancel_requested.is_(False),
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def _overlapping_cancellations(session: AsyncSession, user_id: str, snapshot: dict) -> list[str]:
    selected = {(item["product_id"], item.get("sku_id")) for item in snapshot["items"]}
    pending = await session.execute(select(ReportOrderModel.order_id, ReportOrderModel.report).where(
        ReportOrderModel.kind == "cart", ReportOrderModel.user_id == user_id,
        ReportOrderModel.status == "pending", ReportOrderModel.cancel_requested.is_(True),
    ))
    return [
        order_id for order_id, report in pending
        if any((item["product_id"], item.get("sku_id")) in selected for item in report["items"])
    ]


_OVERLAP_MESSAGE = "部分选中商品的旧订单正在取消。取消勾选这些商品即可结算其他商品，也可以稍后重试。"


async def chat_cart_payment(session: AsyncSession, user_id: str, chat_session_id: str):
    if not chat_session_id or len(chat_session_id) > 64:
        raise HTTPException(422, "请在当前对话里重新发起购物车结算")
    order = await session.scalar(
        select(ReportOrderModel).where(
            ReportOrderModel.kind == "cart", ReportOrderModel.user_id == user_id,
            ReportOrderModel.channel == "agent", ReportOrderModel.chat_session_id == chat_session_id,
        ).order_by(ReportOrderModel.created_at.desc(), ReportOrderModel.order_id.desc()).limit(1)
    )
    if order is None:
        raise HTTPException(409, "当前对话没有待确认的订单，请先说「用支付宝结算购物车」")
    return order


async def quote_cart(session: AsyncSession, user_id: str, item_ids: list[str], chat_session_id: str | None = None):
    provider = cart_provider()
    await lock_buyer(session, user_id)
    pending = await pending_cart_payment(session, user_id, lock=True)
    if pending and pending.environment == "demo" and provider is not None:
        # Demo orders never reach Alipay and can be closed before creating a provider quote.
        pending.status = "closed"
        await session.flush()
        pending = None
    if pending and _expired(pending):
        # Release database locks before calling Alipay. An inconclusive check
        # must leave the old order pending and continue blocking new payments.
        order_id = pending.order_id
        await session.commit()
        pending = await _refresh(session, order_id, user_id, "cart")
        if pending.status == "paid":
            return pending

        if pending.status == "closed" or pending.cancel_requested:
            # Another checkout may have started while the gateway was being queried.
            await session.commit()
            await lock_buyer(session, user_id)
            pending = await pending_cart_payment(session, user_id, lock=True)
    snapshot, amount = await snapshot_cart(session, user_id, item_ids)
    cancellations = await _overlapping_cancellations(session, user_id, snapshot)
    if cancellations:
        await session.commit()
        for order_id in cancellations:
            previous = await _refresh(session, order_id, user_id, "cart")
            if previous.status == "paid":
                return previous
        await session.commit()
        await lock_buyer(session, user_id)
        pending = await pending_cart_payment(session, user_id, lock=True)
        snapshot, amount = await snapshot_cart(session, user_id, item_ids)
        if await _overlapping_cancellations(session, user_id, snapshot):
            raise HTTPException(409, _OVERLAP_MESSAGE)
    if pending:
        _check_provider(pending, provider)
        if pending.report != snapshot or pending.amount_fen != amount:
            previous = f"¥{pending.amount_fen / 100:,.2f}"
            current = f"¥{amount / 100:,.2f}"
            raise HTTPException(
                409, f"已有一笔待付款订单（{previous}），与本次选择（{current}）不同。"
                "请先查看旧订单，待订单完成或关闭后再结算当前商品。",
            )
        return pending
    now = datetime.now(timezone.utc)
    order = ReportOrderModel(
        order_id=uuid4().hex, user_id=user_id, kind="cart", chat_session_id=chat_session_id,
        channel="agent" if chat_session_id else "web", environment=settings.report_payment_mode,
        amount_fen=amount, app_id=provider.app_id if provider else "", seller_id=provider.seller_id if provider else "",
        status="quoted", report=snapshot, created_at=now, expires_at=now + timedelta(minutes=30),
    )
    session.add(order)
    await session.commit()
    return order


async def confirm_cart(session: AsyncSession, user_id: str, order_id: str) -> tuple[ReportOrderModel, str | None]:
    await lock_buyer(session, user_id)
    order = await _order(session, order_id, user_id, lock=True, kind="cart")
    if order.status == "paid":
        return order, None
    if order.cancel_requested:
        raise HTTPException(409, "这笔订单已申请取消，请返回购物车重新结算")
    provider = cart_provider()
    _check_provider(order, provider)
    if order.status == "closed" or _expired(order):
        raise HTTPException(409, "报价已过期。若已付款，请先查询这笔订单")
    if order.status == "quoted":
        other = await pending_cart_payment(session, user_id, lock=True)
        if other is not None:
            raise HTTPException(409, "已有一笔待支付订单，请先到购物车查看并处理")
        if await _overlapping_cancellations(session, user_id, order.report):
            raise HTTPException(409, _OVERLAP_MESSAGE)
        live, amount = await snapshot_cart(session, user_id, list(order.report["item_versions"]))
        if live != order.report or amount != order.amount_fen:
            raise HTTPException(409, "购物车商品、价格或地址已变更，请重新报价")
        order.status = "pending"

    checkout_url = provider.checkout_url(order) if provider else None
    await session.commit()
    return order, checkout_url
