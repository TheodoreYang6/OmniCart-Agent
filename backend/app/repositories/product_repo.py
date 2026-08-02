"""产品仓库 — 工厂重导出。

根据 USE_POSTGRES 配置自动选择：
- True  → PgProductRepository（PostgreSQL）
- False → JsonProductRepository（JSON 文件，默认）

保持向后兼容：`from app.repositories.product_repo import ProductRepository` 仍然可用。
"""

import logging
from pathlib import Path

from app.core.config import USE_POSTGRES, DATABASE_URL
from app.repositories.base_product_repo import BaseProductRepository
from app.repositories.json_product_repo import JsonProductRepository
from app.repositories.pg_product_repo import PgProductRepository

logger = logging.getLogger(__name__)

_pg_available: bool | None = None  # None=未检查, True=可用, False=不可用


def _check_pg() -> bool:
    """检查 PostgreSQL 是否真正可用（带缓存）"""
    global _pg_available
    if _pg_available is not None:
        return _pg_available
    if not USE_POSTGRES:
        _pg_available = False
        return False
    try:
        from app.core.database import run_async
        run_async(_check_pg_async())
        _pg_available = True
        return True
    except Exception:
        logger.warning("PostgreSQL unreachable — falling back to JSON file mode")
        _pg_available = False
        return False


async def _check_pg_async():
    import asyncpg
    # asyncpg 不接受 SQLAlchemy 的 "+asyncpg" 协议前缀，需转换为纯 postgresql://
    pg_url = DATABASE_URL.replace("+asyncpg", "") if "+asyncpg" in DATABASE_URL else DATABASE_URL
    conn = await asyncpg.connect(pg_url, timeout=3)
    await conn.close()


_ProductRepository: type | None = None


def __getattr__(name: str):
    """惰性解析 ProductRepository，避免模块导入时触发网络 I/O。"""
    if name == "ProductRepository":
        global _ProductRepository
        if _ProductRepository is None:
            if USE_POSTGRES and _check_pg():
                _ProductRepository = PgProductRepository
            else:
                _ProductRepository = JsonProductRepository
        return _ProductRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_product_repo(data_root: Path | None = None) -> BaseProductRepository:
    """返回当前活动的产品仓库实例（PG 不可用时自动降级 JSON）。"""
    if USE_POSTGRES and _check_pg():
        return PgProductRepository()
    return JsonProductRepository(data_root=data_root)
