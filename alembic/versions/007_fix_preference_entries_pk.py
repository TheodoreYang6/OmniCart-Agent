"""fix: user_preference_entries 缺少 primary key 约束 + 自增序列

Revision ID: 007
Revises: 006
Create Date: 2026-06-08
"""

from typing import Sequence, Union
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE SEQUENCE IF NOT EXISTS user_preference_entries_id_seq
        OWNED BY user_preference_entries.id
    """)
    op.execute("""
        ALTER TABLE user_preference_entries
        ALTER COLUMN id SET DEFAULT nextval('user_preference_entries_id_seq')
    """)
    op.execute("ALTER TABLE user_preference_entries ADD PRIMARY KEY (id)")


def downgrade():
    op.execute("ALTER TABLE user_preference_entries DROP CONSTRAINT user_preference_entries_pkey")
    op.execute("ALTER TABLE user_preference_entries ALTER COLUMN id DROP DEFAULT")
