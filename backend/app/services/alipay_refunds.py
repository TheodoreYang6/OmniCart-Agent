"""Apply provider-verified refund receipts to shopping orders."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import OrderModel
from app.models.report_order import AlipayRefundModel
from app.services.payment_settlement import _check_provider, _order, _provider


async def reconcile_refund(session: AsyncSession, payment_id: str, request_no: str) -> dict:
    payment = await _order(session, payment_id, kind="cart")
    if payment.status != "paid" or not payment.trade_no or payment.environment not in {"sandbox", "production"}:
        raise HTTPException(409, "订单没有可核对的支付宝付款流水")
    provider = _provider()
    _check_provider(payment, provider)
    trade_no = payment.trade_no
    await session.commit()
    try:
        receipt = await provider.query_refund(trade_no, request_no)
    except (ValueError, httpx.HTTPError):
        raise HTTPException(502, "暂时无法核实支付宝退款") from None
    if receipt.get("code") != "10000" or receipt.get("refund_status") != "REFUND_SUCCESS":
        return {"order_id": payment_id, "verified": False}
    if (receipt.get("out_trade_no") != payment_id or receipt.get("trade_no") != trade_no
            or receipt.get("out_request_no") != request_no):
        raise HTTPException(409, "退款流水与订单不符")
    try:
        amount = Decimal(str(receipt["refund_amount"])) * 100
        if not amount.is_finite() or not 0 < amount <= payment.amount_fen or amount != amount.to_integral_value():
            raise ValueError
    except (KeyError, InvalidOperation, ValueError):
        raise HTTPException(409, "退款金额无效") from None

    payment = await _order(session, payment_id, lock=True, kind="cart")
    order = await session.get(OrderModel, payment_id, with_for_update=True)
    if order is None or order.user_id != payment.user_id:
        raise HTTPException(409, "订单和支付宝流水尚未完成对账")
    existing = await session.get(AlipayRefundModel, (payment_id, request_no))
    if existing and existing.amount_fen != int(amount):
        raise HTTPException(409, "退款流水金额发生变化")
    if existing is None:
        session.add(AlipayRefundModel(order_id=payment_id, request_no=request_no,
                                      amount_fen=int(amount), verified_at=datetime.now(timezone.utc)))
        await session.flush()
    refunded_fen = await session.scalar(
        select(func.sum(AlipayRefundModel.amount_fen)).where(AlipayRefundModel.order_id == payment_id)
    )
    if refunded_fen > payment.amount_fen:
        raise HTTPException(409, "累计退款超过付款金额")
    payment.refunded_fen = refunded_fen
    order.status = "refunded" if refunded_fen == payment.amount_fen else "partially_refunded"
    await session.commit()
    return {"order_id": payment_id, "verified": True, "status": order.status, "refunded_fen": int(refunded_fen)}
