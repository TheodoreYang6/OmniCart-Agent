"""Allow a new cart payment while an unrelated cancellation is pending."""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

_INDEX = "ix_cart_payment_pending_user"
_PENDING = "kind = 'cart' AND status = 'pending'"


def upgrade():
    op.drop_index(_INDEX, table_name="report_orders")
    op.create_index(
        _INDEX, "report_orders", ["user_id"], unique=True,
        postgresql_where=sa.text(_PENDING + " AND NOT cancel_requested"),
    )


def downgrade():
    op.drop_index(_INDEX, table_name="report_orders")
    op.create_index(_INDEX, "report_orders", ["user_id"], unique=True, postgresql_where=sa.text(_PENDING))
