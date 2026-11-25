"""Shared payment processing for report and cart orders."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.report_order import ReportOrderModel
from app.services.alipay_report_gateway import get_alipay_report_gateway
from app.services.cart_payment import fulfill_cart

PAID_STATES = {"TRADE_SUCCESS", "TRADE_FINISHED"}


def _provider():
    mode = settings.report_payment_mode
    if mode == "demo" and settings.host in {"127.0.0.1", "localhost", "::1"}:
        return None
    if mode in {"sandbox", "production"}:
        try:
            return get_alipay_report_gateway(mode)
        except (ValueError, TypeError, OSError):
            raise HTTPException(503, "支付宝商户配置不完整或无效") from None
    raise HTTPException(503, "当前未启用支付宝收款")


async def _order(session: AsyncSession, order_id: str, user_id: str | None = None, *, lock: bool = False,
                 kind: str | None = "report"):
    statement = select(ReportOrderModel).where(ReportOrderModel.order_id == order_id)
    if kind is not None:
        statement = statement.where(ReportOrderModel.kind == kind)
    if user_id is not None:
        statement = statement.where(ReportOrderModel.user_id == user_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(statement)
    if row is None:
        raise HTTPException(404, "支付订单不存在")
    return row


def _check_provider(order, provider):
    if order.environment != settings.report_payment_mode or (
        provider and (order.app_id != provider.app_id or order.seller_id != provider.seller_id)
    ):
        raise HTTPException(409, "订单对应的支付环境或商户已变更")



def fulfillment_status(order: ReportOrderModel) -> str:
    refunded = order.refunded_fen or 0
    if not refunded:
        return order.status
    return "refunded" if refunded == order.amount_fen else "partially_refunded"


def _expired(order) -> bool:
    return order.expires_at <= datetime.now(timezone.utc)


def _reconcile(order: ReportOrderModel, trade: dict) -> None:
    """Apply trusted gateway state under a row lock."""
    try:
        amount = Decimal(str(trade["total_amount"]))
    except (KeyError, InvalidOperation):
        raise HTTPException(409, "支付宝交易金额无效") from None
    if trade.get("out_trade_no") != order.order_id or amount != Decimal(order.amount_fen) / 100:
        raise HTTPException(409, "支付宝交易与报价不符")
    if trade.get("seller_id", order.seller_id) != order.seller_id:
        raise HTTPException(409, "支付宝收款方与订单不符")

    status = trade.get("trade_status")
    if status == "TRADE_CLOSED" and order.status == "pending":
        order.status = "closed"
    if status not in PAID_STATES:
        return
    trade_no = trade.get("trade_no")
    if not isinstance(trade_no, str) or not trade_no or len(trade_no) > 64:
        raise HTTPException(409, "缺少有效的支付宝交易号")
    if order.status == "paid" and order.trade_no == trade_no:
        return
    if order.status not in {"pending", "closed"}:
        raise HTTPException(409, "本地订单状态与支付宝交易不符")
    order.trade_no = trade_no
    order.paid_at = datetime.now(timezone.utc)
    order.status = "paid"


async def _apply_trade(session: AsyncSession, order: ReportOrderModel, trade: dict) -> None:
    was_paid = order.status == "paid"
    _reconcile(order, trade)
    if not was_paid and order.status == "paid" and order.kind == "cart":
        await fulfill_cart(session, order)


async def _refresh(session: AsyncSession, order_id: str, user_id: str, kind: str):
    order = await _order(session, order_id, user_id, kind=kind)
    can_recover = order.status == "closed" and order.environment in {"sandbox", "production"}
    if order.status != "pending" and not can_recover:
        return order
    provider = _provider()
    _check_provider(order, provider)
    if provider is None:
        if _expired(order):
            order = await _order(session, order_id, user_id, lock=True, kind=kind)
            if order.status == "pending":
                order.status = "closed"
                await session.commit()
        return order
    expired = _expired(order)
    await session.commit()
    try:
        result = await provider.query(order_id)
        if (expired and result.get("code") == "10000" and result.get("out_trade_no") == order_id
                and result.get("trade_status") == "WAIT_BUYER_PAY"):
            # Re-query even on a failed close: payment may have won the race.
            await provider.close(order_id)
            result = await provider.query(order_id)
    except (ValueError, httpx.HTTPError):
        raise HTTPException(502, "暂时无法核实支付宝交易，请稍后查询") from None
    order = await _order(session, order_id, user_id, lock=True, kind=kind)
    if result.get("code") == "40004" and result.get("sub_code") == "ACQ.TRADE_NOT_EXIST":
        if order.status == "pending" and _expired(order):
            order.status = "closed"
            await session.commit()
        return order
    if result.get("code") != "10000":
        raise HTTPException(502, "支付宝暂未返回可核实的交易状态")
    await _apply_trade(session, order, result)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(409, "支付宝交易号已关联其他订单") from None
    return order


async def _demo_pay(session: AsyncSession, request: Request, order_id: str, user_id: str, kind: str):
    if (settings.report_payment_mode != "demo" or not request.client
            or request.client.host not in {"127.0.0.1", "::1"}):
        raise HTTPException(404)
    _provider()
    order = await _order(session, order_id, user_id, lock=True, kind=kind)
    _check_provider(order, None)
    if order.status == "paid":
        return order
    if order.status != "pending" or _expired(order):
        raise HTTPException(409, "请确认一笔有效的演示订单")
    await _apply_trade(session, order, {
        "out_trade_no": order.order_id, "trade_no": "demo_" + order.order_id,
        "total_amount": str(Decimal(order.amount_fen) / 100), "trade_status": "TRADE_SUCCESS",
    })
    await session.commit()
    return order
