"""Track verified refunds and allow the full Alipay amount range."""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("report_orders", "amount_fen", type_=sa.BigInteger())
    op.add_column("report_orders", sa.Column("refunded_fen", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_table(
        "alipay_refunds",
        sa.Column("order_id", sa.String(32), sa.ForeignKey("report_orders.order_id"), primary_key=True),
        sa.Column("request_no", sa.String(64), primary_key=True),
        sa.Column("amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_fen > 0", name="ck_alipay_refund_amount"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM alipay_refunds)")):
        raise RuntimeError("Reconcile stored refunds before downgrading")
    op.drop_table("alipay_refunds")
    op.drop_column("report_orders", "refunded_fen")
    op.alter_column("report_orders", "amount_fen", type_=sa.Integer())
