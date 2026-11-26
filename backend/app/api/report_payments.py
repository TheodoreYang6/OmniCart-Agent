"""Generate free shopping reports and reconcile existing Alipay transactions."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session_sync
from app.core.identity import Actor, require_user, resolve_actor
from app.models.report_order import ReportOrderModel
from app.services.payment_settlement import (
    _apply_trade, _check_provider, _expired, _order, _provider, _refresh,
)
from app.services.shopping_report import REPORT_TITLE, build_shopping_report, list_report_categories

router = APIRouter(prefix="/api/report-payments", tags=["shopping reports"])
OrderId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]


class GenerateRequest(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    budget_fen: int = Field(gt=0, le=100_000_000, strict=True)
    channel: Literal["web", "agent"] = "web"


class ConfirmRequest(BaseModel):
    confirmed: Literal[True]


async def _session():
    factory = get_session_sync()
    if factory is None:
        raise HTTPException(503, "该功能需要 PostgreSQL")
    async with factory() as session:
        yield session


def _user(actor: Actor = Depends(resolve_actor)) -> Actor:
    return require_user(actor)


def _view(order: ReportOrderModel, *, include_report: bool = True) -> dict:
    return {
        "order_id": order.order_id,
        "title": REPORT_TITLE,
        "category": order.report["category"],
        "budget_fen": order.report["budget_fen"],
        "candidate_count": order.report["candidate_count"],
        "amount_fen": order.amount_fen,
        "currency": "CNY",
        "channel": order.channel,
        "mode": order.environment,
        "status": order.status,
        "created_at": order.created_at,
        "expires_at": order.expires_at,
        "expired": order.environment != "free" and _expired(order),
        "paid_at": order.paid_at,
        "trade_no": order.trade_no if order.status == "paid" else None,
        "report": order.report if include_report and order.status in {"delivered", "paid"} else None,
    }


@router.get("/service")
async def discover_service(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        skillpay_link = urlsplit(settings.report_skillpay_url)
        skillpay_url = settings.report_skillpay_url if (
            skillpay_link.scheme == "https"
            and skillpay_link.netloc == "aipayapi.alipay.com"
            and skillpay_link.path == "/skillpay/ct"
            and skillpay_link.query.startswith("c=")
        ) else None
    except ValueError:
        skillpay_url = None
    return {
        "service_id": "omnicart.shopping-report",
        "title": REPORT_TITLE,
        "description": "按品类和预算比较商品，查看价格差异、FAQ 和评价样本。",
        "amount_fen": 0,
        "currency": "CNY",
        "mode": "free",
        "enabled": get_session_sync() is not None,
        "skillpay_url": skillpay_url,
        "generate_path": "/api/report-payments/orders",
    }


@router.get("/categories")
async def categories(session: AsyncSession = Depends(_session)):
    return await list_report_categories(session)


@router.post("/orders", status_code=201)
async def generate(req: GenerateRequest, response: Response, actor: Actor = Depends(_user),
                   session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    report = await build_shopping_report(session, req.category.strip(), req.budget_fen)
    if report is None:
        raise HTTPException(422, "该品类在预算内少于两款商品，请调整品类或预算")
    now = datetime.now(timezone.utc)
    order = ReportOrderModel(
        order_id=uuid4().hex, user_id=actor.user_id, amount_fen=0,
        channel=req.channel, environment="free", status="delivered", app_id="", seller_id="",
        report=report, created_at=now, expires_at=now,
    )
    session.add(order)
    await session.commit()
    return _view(order)


@router.get("/orders")
async def list_orders(response: Response, actor: Actor = Depends(_user), session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    results = await session.scalars(select(ReportOrderModel).where(
        ReportOrderModel.user_id == actor.user_id, ReportOrderModel.kind == "report",
    ).order_by(ReportOrderModel.created_at.desc()).limit(30))
    return [_view(order, include_report=False) for order in results]


@router.get("/orders/{order_id}")
async def read_order(order_id: OrderId, response: Response, actor: Actor = Depends(_user),
                     session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return _view(await _order(session, order_id, actor.user_id))


@router.post("/orders/{order_id}/confirm")
async def confirm_order(order_id: OrderId, _: ConfirmRequest, response: Response, actor: Actor = Depends(_user),
                        session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    order = await _order(session, order_id, actor.user_id)
    if order.status in {"delivered", "paid"}:
        return _view(order)
    raise HTTPException(410, "选购报告已免费，请重新生成报告")


@router.post("/orders/{order_id}/refresh")
async def refresh_order(order_id: OrderId, response: Response, actor: Actor = Depends(_user),
                        session: AsyncSession = Depends(_session)):
    response.headers["Cache-Control"] = "private, no-store"
    order = await _order(session, order_id, actor.user_id)
    if order.environment == "free":
        return _view(order)
    return _view(await _refresh(session, order_id, actor.user_id, "report"))


@router.post("/alipay/notify", response_class=PlainTextResponse)
async def alipay_notify(request: Request, session: AsyncSession = Depends(_session)):
    try:
        if settings.report_payment_mode not in {"sandbox", "production"}:
            return "failure"
        provider = _provider()
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
            return "failure"
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 32_768:
                return "failure"
            body.extend(chunk)
        pairs = parse_qsl(body.decode(), keep_blank_values=True, strict_parsing=True, max_num_fields=100, errors="strict")
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return "failure"
        if (not provider.verify_notification(fields) or fields.get("app_id") != provider.app_id
                or fields.get("seller_id") != provider.seller_id or not fields.get("out_trade_no")):
            return "failure"
        order = await _order(session, fields["out_trade_no"], lock=True, kind=None)
        _check_provider(order, provider)
        await _apply_trade(session, order, fields)
        await session.commit()
    except (HTTPException, IntegrityError, ValueError):
        return "failure"
    return "success"
