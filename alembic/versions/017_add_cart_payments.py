"""Allow the Alipay ledger to store cart checkout sessions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_orders", sa.Column("kind", sa.String(16), nullable=False, server_default="report"))
    op.add_column("report_orders", sa.Column("chat_session_id", sa.String(64)))
    op.create_index(
        "ix_cart_payment_pending_user", "report_orders", ["user_id"], unique=True,
        postgresql_where=sa.text("kind = 'cart' AND status = 'pending'"),
    )
    op.add_column("orders", sa.Column("shipping_address", JSONB, nullable=True))


def downgrade():
    ledger = op.get_bind()
    if ledger.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM report_orders WHERE kind = 'cart')")):
        raise RuntimeError("Export and reconcile the cart payment ledger before downgrading")
    op.drop_column("orders", "shipping_address")
    op.drop_index("ix_cart_payment_pending_user", table_name="report_orders")
    op.drop_column("report_orders", "chat_session_id")
    op.drop_column("report_orders", "kind")
