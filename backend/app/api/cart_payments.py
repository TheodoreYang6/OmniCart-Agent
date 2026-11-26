"""Authenticated web entry points for cart quotes and payment status."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_payments import ConfirmRequest, OrderId, _session, _user
from app.core.config import settings
from app.core.identity import Actor
from app.models.report_order import ReportOrderModel
from app.services.checkout_payment import cart_provider, confirm_cart, pending_cart_payment, quote_cart
from app.services.payment_settlement import _demo_pay, _expired, _order, _refresh, fulfillment_status

router = APIRouter(prefix="/api/cart-payments", tags=["cart payments"])


class CartQuoteRequest(BaseModel):
    item_ids: list[str] = Field(default_factory=list, max_length=100)


def _view(order: ReportOrderModel) -> dict:
    refunded = order.refunded_fen or 0
    return {
        "order_id": order.order_id, "amount_fen": order.amount_fen, "status": fulfillment_status(order), "refunded_fen": refunded,
        "mode": order.environment, "expired": _expired(order),
        "cancel_requested": order.cancel_requested,
        "items": order.report["items"], "address": order.report["address"],
        "trade_no": order.trade_no if order.status == "paid" else None,
    }


@router.get("/service")
async def service(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        cart_provider()
        enabled = settings.use_postgres
    except HTTPException:
        enabled = False
    return {"enabled": enabled, "mode": settings.report_payment_mode}


@router.get("/active")
async def active(response: Response, actor: Actor = Depends(_user), session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    order = await pending_cart_payment(session, actor.user_id)
    if order is None or order.cancel_requested or (
        order.environment == "demo" and (settings.report_payment_mode != "demo" or _expired(order))
    ):
        return None
    return _view(order)


@router.post("/orders", status_code=201)
async def quote(req: CartQuoteRequest, actor: Actor = Depends(_user), session: AsyncSession = Depends(_session)):
    return _view(await quote_cart(session, actor.user_id, req.item_ids))


@router.get("/orders/{order_id}")
async def status(order_id: OrderId, response: Response, actor: Actor = Depends(_user),
                 session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return _view(await _order(session, order_id, actor.user_id, kind="cart"))


@router.post("/orders/{order_id}/confirm")
async def confirm(order_id: OrderId, _: ConfirmRequest, response: Response, actor: Actor = Depends(_user),
                  session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    order, checkout_url = await confirm_cart(session, actor.user_id, order_id)
    return {**_view(order), "checkout_url": checkout_url}


@router.post("/orders/{order_id}/refresh")
async def refresh(order_id: OrderId, response: Response, actor: Actor = Depends(_user),
                  session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return _view(await _refresh(session, order_id, actor.user_id, "cart"))


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: OrderId, _: ConfirmRequest, response: Response, actor: Actor = Depends(_user),
                 session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return _view(await _refresh(session, order_id, actor.user_id, "cart", cancel=True))


@router.post("/orders/{order_id}/demo-pay")
async def demo_pay(order_id: OrderId, _: ConfirmRequest, request: Request, response: Response,
                   actor: Actor = Depends(_user), session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return _view(await _demo_pay(session, request, order_id, actor.user_id, "cart"))
