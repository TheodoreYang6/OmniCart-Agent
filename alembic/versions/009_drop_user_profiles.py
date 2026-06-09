"""drop user_profiles — 已被 user_preference_entries 完全替代，无任何引用

Revision ID: 009
Revises: 008
Create Date: 2026-06-08
"""

from typing import Sequence, Union
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.drop_table("user_profiles")


def downgrade():
    pass
