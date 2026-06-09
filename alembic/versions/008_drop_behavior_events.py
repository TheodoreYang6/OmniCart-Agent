"""drop behavior_events — 无人读取，conversation_messages + cart_items 已覆盖所有行为数据

Revision ID: 008
Revises: 007
Create Date: 2026-06-08
"""

from typing import Sequence, Union
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.drop_table("behavior_events")


def downgrade():
    pass  # 不恢复
