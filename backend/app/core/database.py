"""Async SQLAlchemy 2.0 engine + session factory for PostgreSQL."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import DATABASE_URL, USE_POSTGRES

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine():
    global _engine, _session_factory
    if not USE_POSTGRES or not DATABASE_URL:
        return
    _engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5, max_overflow=10)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """异步上下文管理器，获取一个 DB 会话。"""
    if _session_factory is None:
        _create_engine()
    if _session_factory is None:
        raise RuntimeError("PostgreSQL is not configured (DATABASE_URL is empty)")
    async with _session_factory() as session:
        yield session


def get_session_sync():
    """同步获取会话工厂（供 sync 包装器使用）。"""
    if _session_factory is None:
        _create_engine()
    return _session_factory


async def init_db():
    """应用启动时建表（若无 Alembic 可先用 create_all）。"""
    if not USE_POSTGRES:
        return
    from app.models import Base
    if _engine is None:
        _create_engine()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """应用关闭时释放连接池。"""
    if _engine:
        await _engine.dispose()
