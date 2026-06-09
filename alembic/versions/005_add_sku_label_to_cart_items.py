"""add sku_label to cart_items — 购物车展示所选规格文字

Revision ID: 005
Revises: 004
Create Date: 2026-06-08

添加 sku_label 列，存储加购时的 SKU 可读描述（如"256GB · 黑色"），
购物车列表无需回查商品表即可直接展示。
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    op.add_column("cart_items", sa.Column("sku_label", sa.String(256), nullable=False, server_default=""))


def downgrade():
    op.drop_column("cart_items", "sku_label")
