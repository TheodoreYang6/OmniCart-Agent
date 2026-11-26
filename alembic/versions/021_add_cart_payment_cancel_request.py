"""Record cancellation requests while the payment link may still be usable."""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_orders", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("report_orders", "cancel_requested")
