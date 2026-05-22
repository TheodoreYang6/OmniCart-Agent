"""产品仓库 — 工厂重导出。

根据 USE_POSTGRES 配置自动选择：
- True  → PgProductRepository（PostgreSQL）
- False → JsonProductRepository（JSON 文件，默认）

保持向后兼容：`from app.repositories.product_repo import ProductRepository` 仍然可用。
"""

from pathlib import Path

from app.core.config import USE_POSTGRES
from app.repositories.base_product_repo import BaseProductRepository
from app.repositories.json_product_repo import JsonProductRepository
from app.repositories.pg_product_repo import PgProductRepository

# 向后兼容的 ProductRepository 别名
if USE_POSTGRES:
    ProductRepository = PgProductRepository  # type: ignore[assignment]
else:
    ProductRepository = JsonProductRepository  # type: ignore[assignment]


def get_product_repo(data_root: Path | None = None) -> BaseProductRepository:
    """返回当前活动的产品仓库实例。"""
    if USE_POSTGRES:
        return PgProductRepository()
    return JsonProductRepository(data_root=data_root)
