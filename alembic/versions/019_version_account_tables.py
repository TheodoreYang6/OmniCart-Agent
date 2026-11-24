"""Version user and address tables while retaining tables from existing installs."""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade():
    tables = sa.MetaData()
    users = sa.Table(
        "users", tables,
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("email", sa.String(128)), sa.Column("phone", sa.String(64)),
        sa.Column("avatar_url", sa.String(512)), sa.Column("is_active", sa.Boolean()),
        sa.Column("token", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    addresses = sa.Table(
        "addresses", tables,
        sa.Column("address_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False), sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("province", sa.String(32)), sa.Column("city", sa.String(32)),
        sa.Column("district", sa.String(32)), sa.Column("detail", sa.String(256)),
        sa.Column("is_default", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    for table in (users, addresses):
        table.create(bind, checkfirst=True)
    sa.Index("ix_users_username", users.c.username, unique=True).create(bind, checkfirst=True)
    sa.Index("ix_addresses_user_id", addresses.c.user_id).create(bind, checkfirst=True)


def downgrade():
    # Earlier versions rely on the same tables, including existing accounts and addresses.
    pass
