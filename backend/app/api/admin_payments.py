"""Authenticated operations for replaying settlement and checking refunds."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_payments import OrderId, _session
from app.core.identity import require_admin
from app.services.alipay_refunds import reconcile_refund
from app.services.payment_settlement import _order, _refresh, fulfillment_status

router = APIRouter(prefix="/api/admin/payments", dependencies=[Depends(require_admin)])


class ReconcileRequest(BaseModel):
    order_ids: list[OrderId] = Field(min_length=1, max_length=20)


class RefundRequest(BaseModel):
    request_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


@router.post("/reconcile")
async def reconcile(req: ReconcileRequest, session: AsyncSession = Depends(_session)):
    results = []
    for order_id in dict.fromkeys(req.order_ids):
        try:
            order = await _order(session, order_id, kind=None)
            order = await _refresh(session, order_id, order.user_id, order.kind, recover_closed=True)
            results.append({"order_id": order_id, "status": fulfillment_status(order)})
        except HTTPException as exc:
            results.append({"order_id": order_id, "error": exc.detail})
        finally:
            await session.rollback()
    return results


@router.post("/{order_id}/refund/reconcile")
async def refund(order_id: OrderId, req: RefundRequest, session: AsyncSession = Depends(_session)):
    return await reconcile_refund(session, order_id, req.request_no)
