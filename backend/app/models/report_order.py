"""Orders and immutable delivery snapshots for paid shopping reports."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ReportOrderModel(Base):
    __tablename__ = "report_orders"
    __table_args__ = (
        CheckConstraint("amount_fen > 0", name="ck_report_order_amount"),
        CheckConstraint("status IN ('quoted', 'pending', 'paid', 'closed')", name="ck_report_order_status"),
        Index("ix_cart_payment_pending_user", "user_id", unique=True,
              postgresql_where=text("kind = 'cart' AND status = 'pending'")),
    )

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="report", server_default="report")
    chat_session_id: Mapped[str | None] = mapped_column(String(64))
    amount_fen: Mapped[int] = mapped_column(BigInteger)
    refunded_fen: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    channel: Mapped[str] = mapped_column(String(16))
    environment: Mapped[str] = mapped_column(String(16))
    app_id: Mapped[str] = mapped_column(String(32))
    seller_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    report: Mapped[dict] = mapped_column(JSONB)
    trade_no: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AlipayRefundModel(Base):
    __tablename__ = "alipay_refunds"
    __table_args__ = (CheckConstraint("amount_fen > 0", name="ck_alipay_refund_amount"),)

    order_id: Mapped[str] = mapped_column(ForeignKey("report_orders.order_id"), primary_key=True)
    request_no: Mapped[str] = mapped_column(String(64), primary_key=True)
    amount_fen: Mapped[int] = mapped_column(BigInteger)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
