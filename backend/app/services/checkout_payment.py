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
        ReportOrderModel.status == "pending",
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


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
    if pending:
        if not _expired(pending):
            return pending

        # Release database locks before calling Alipay. An inconclusive check
        # must leave the old order pending and continue blocking new payments.
        order_id = pending.order_id
        await session.commit()
        pending = await _refresh(session, order_id, user_id, "cart")
        if pending.status != "closed":
            return pending

        # Another checkout may have started while the gateway was being queried.
        await session.commit()
        await lock_buyer(session, user_id)
        active = await pending_cart_payment(session, user_id, lock=True)
        if active is not None:
            return active
    snapshot, amount = await snapshot_cart(session, user_id, item_ids)
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
    provider = cart_provider()
    _check_provider(order, provider)
    if order.status == "closed" or _expired(order):
        raise HTTPException(409, "报价已过期。若已付款，请先查询这笔订单")
    if order.status == "quoted":
        other = await pending_cart_payment(session, user_id, lock=True)
        if other is not None:
            raise HTTPException(409, "已有一笔待支付订单，请先到购物车查看并处理")
        live, amount = await snapshot_cart(session, user_id, list(order.report["item_versions"]))
        if live != order.report or amount != order.amount_fen:
            raise HTTPException(409, "购物车商品、价格或地址已变更，请重新报价")
        order.status = "pending"

    checkout_url = provider.checkout_url(order) if provider else None
    await session.commit()
    return order, checkout_url
