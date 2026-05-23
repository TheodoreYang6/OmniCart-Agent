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
        import asyncpg
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，用 asyncio.run()
            asyncio.run(_check_pg_async())
            _pg_available = True
            return True
        # 有运行中的循环，用 nest_asyncio
        import nest_asyncio
        nest_asyncio.apply(loop)
        loop.run_until_complete(_check_pg_async())
        _pg_available = True
        return True
    except Exception:
        logger.warning("PostgreSQL unreachable — falling back to JSON file mode")
        _pg_available = False
        return False


async def _check_pg_async():
    import asyncpg
    conn = await asyncpg.connect(DATABASE_URL, timeout=3)
    await conn.close()


# 向后兼容的 ProductRepository 别名
if USE_POSTGRES and _check_pg():
    ProductRepository = PgProductRepository  # type: ignore[assignment]
else:
    ProductRepository = JsonProductRepository  # type: ignore[assignment]


def get_product_repo(data_root: Path | None = None) -> BaseProductRepository:
    """返回当前活动的产品仓库实例（PG 不可用时自动降级 JSON）。"""
    if USE_POSTGRES and _check_pg():
        return PgProductRepository()
    return JsonProductRepository(data_root=data_root)
