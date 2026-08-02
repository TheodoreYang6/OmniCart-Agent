"""add product derived columns + trigram search (V5 架构优化)

新增派生聚合列（avg_rating/review_count/positive_count/negative_count/risk_tags）
+ 关键词检索文本列 search_text + pg_trgm GIN 索引 + avg_rating 排序索引。

- search_text 回填：本迁移用 SQL 拼接 title+brand+category+sub_category+营销描述。
- 评价派生列（avg_rating 等）回填：由 scripts/reindex_all.py 用 Python 计算
  (compute_review_aggregates)，口径与 products API 一致。

Revision ID: 011
Revises: 010
Create Date: 2026-07-21
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade():
    # 派生聚合列
    op.add_column("products", sa.Column("avg_rating", sa.Numeric(3, 2), server_default="0"))
    op.add_column("products", sa.Column("review_count", sa.Integer, server_default="0"))
    op.add_column("products", sa.Column("positive_count", sa.Integer, server_default="0"))
    op.add_column("products", sa.Column("negative_count", sa.Integer, server_default="0"))
    op.add_column("products", sa.Column("risk_tags", postgresql.JSONB, nullable=True))
    op.add_column("products", sa.Column("search_text", sa.Text, nullable=True))

    # 回填 search_text（拼接文本，中文用 trigram 匹配无需分词）
    op.execute(
        """
        UPDATE products SET search_text =
            coalesce(title,'') || ' ' || coalesce(brand,'') || ' ' ||
            coalesce(category,'') || ' ' || coalesce(sub_category,'') || ' ' ||
            coalesce(rag_knowledge->>'marketing_description','')
        """
    )

    # pg_trgm 扩展 + GIN 索引（子串/模糊关键词检索）
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_search_text_trgm "
        "ON products USING gin (search_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_title_trgm "
        "ON products USING gin (title gin_trgm_ops)"
    )
    # avg_rating 排序索引
    op.create_index("ix_products_avg_rating", "products", ["avg_rating"])


def downgrade():
    op.drop_index("ix_products_avg_rating", table_name="products")
    op.execute("DROP INDEX IF EXISTS ix_products_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_search_text_trgm")
    op.drop_column("products", "search_text")
    op.drop_column("products", "risk_tags")
    op.drop_column("products", "negative_count")
    op.drop_column("products", "positive_count")
    op.drop_column("products", "review_count")
    op.drop_column("products", "avg_rating")
