"""Store free shopping reports alongside existing payment orders."""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_report_order_amount", "report_orders", type_="check")
    op.drop_constraint("ck_report_order_status", "report_orders", type_="check")
    op.create_check_constraint(
        "ck_report_order_delivery", "report_orders",
        "(environment = 'free' AND kind = 'report' AND amount_fen = 0 AND status = 'delivered') OR "
        "(environment <> 'free' AND amount_fen > 0 AND status IN ('quoted', 'pending', 'paid', 'closed'))",
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM report_orders WHERE environment = 'free')")):
        raise RuntimeError("Preserve free reports before downgrading")
    op.drop_constraint("ck_report_order_delivery", "report_orders", type_="check")
    op.create_check_constraint("ck_report_order_amount", "report_orders", "amount_fen > 0")
    op.create_check_constraint(
        "ck_report_order_status", "report_orders", "status IN ('quoted', 'pending', 'paid', 'closed')",
    )
