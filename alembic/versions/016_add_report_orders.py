"""Store paid shopping report orders and delivery snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_orders",
        sa.Column("order_id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("amount_fen", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("app_id", sa.String(32), nullable=False),
        sa.Column("seller_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("report", JSONB, nullable=False),
        sa.Column("trade_no", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("amount_fen > 0", name="ck_report_order_amount"),
        sa.CheckConstraint("status IN ('quoted', 'pending', 'paid', 'closed')", name="ck_report_order_status"),
    )
    op.create_index("ix_report_orders_user_id", "report_orders", ["user_id"])


def downgrade():
    op.drop_table("report_orders")
