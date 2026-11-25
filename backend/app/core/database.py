"""Async SQLAlchemy 2.0 engine + session factory for PostgreSQL.

核心设计（解决 asyncpg "attached to a different loop"）:
- engine/session factory 按事件循环隔离缓存 — asyncpg 连接绑定创建时的
  事件循环，跨循环复用必然崩溃，因此每个循环持有自己的 engine。
- 同步接口桥接使用**常驻**后台循环（bridge loop），协程与其使用的 engine
  始终在同一循环上，兼容 uvloop（不再依赖 nest_asyncio 补丁主循环）。
"""

import asyncio
import threading

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import DATABASE_URL, USE_POSTGRES

# 事件循环 id → (engine, session_factory)
_engines: dict[int, tuple] = {}
_engines_lock = threading.Lock()


def _get_factory_for_current_loop():
    """获取当前运行循环专属的 session factory（必须在协程内调用）。"""
    if not USE_POSTGRES or not DATABASE_URL:
        return None
    loop = asyncio.get_running_loop()
    key = id(loop)
    entry = _engines.get(key)
    if entry is None:
        with _engines_lock:
            entry = _engines.get(key)
            if entry is None:
                engine = create_async_engine(
                    DATABASE_URL, echo=False, pool_size=5, max_overflow=10
                )
                entry = (engine, async_sessionmaker(engine, expire_on_commit=False))
                _engines[key] = entry
    return entry[1]


class _LoopAwareSessionFactory:
    """代理工厂 — 调用时（协程内）按当前循环取对应 engine 的 session。

    保持 `async with factory() as session` 的既有用法不变。
    """

    def __call__(self) -> AsyncSession:
        factory = _get_factory_for_current_loop()
        if factory is None:
            raise RuntimeError("PostgreSQL is not configured (DATABASE_URL is empty)")
        return factory()


_factory_proxy = _LoopAwareSessionFactory()


async def get_session() -> AsyncSession:
    """异步上下文管理器，获取一个 DB 会话。"""
    factory = _get_factory_for_current_loop()
    if factory is None:
        raise RuntimeError("PostgreSQL is not configured (DATABASE_URL is empty)")
    async with factory() as session:
        yield session


def get_session_sync():
    """同步获取会话工厂（供 sync 包装器使用）。未配置 PG 时返回 None。"""
    if not USE_POSTGRES or not DATABASE_URL:
        return None
    return _factory_proxy


async def init_db():
    """Check that the configured database is reachable and migrations are current.

    Raises ``RuntimeError`` with a human-readable message so the readiness
    probe and entrypoint can surface the specific failure (connection vs
    migration mismatch) instead of a generic "unavailable".
    """
    if not USE_POSTGRES:
        return
    from pathlib import Path
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    migrations = Path(__file__).resolve().parents[3] / "alembic"
    expected = set(ScriptDirectory(str(migrations)).get_heads())
    try:
        async with get_session_sync()() as session:
            version_table = await session.scalar(text("SELECT to_regclass('alembic_version')"))
            current = set()
            if version_table is not None:
                current.update((await session.scalars(text("SELECT version_num FROM alembic_version"))).all())
    except Exception as exc:
        raise RuntimeError(
            "Database is configured but not reachable. "
            "Check DATABASE_URL and ensure PostgreSQL is running. "
            f"Original error: {exc}"
        ) from exc
    if not current:
        raise RuntimeError(
            "Database has no Alembic revision. Run 'alembic upgrade head' for an empty database. "
            "For an existing unversioned database, see docs/PAYATHON.md."
        )
    if current != expected:
        missing = expected - current
        extra = current - expected
        detail = []
        if missing:
            detail.append(f"pending migrations: {', '.join(sorted(missing))}")
        if extra:
            detail.append(f"unexpected heads: {', '.join(sorted(extra))}")
        raise RuntimeError(
            "Database migration required. Run 'alembic upgrade head'. "
            + "; ".join(detail)
        )


async def close_db():
    """应用关闭时释放当前循环的连接池；桥接循环的池随 daemon 线程退出释放。"""
    loop_id = id(asyncio.get_running_loop())
    entry = _engines.pop(loop_id, None)
    if entry:
        await entry[0].dispose()


# ---- Async-to-Sync Bridge (供 PG 仓库在同步接口中桥接异步查询) ----

_bridge_loop: asyncio.AbstractEventLoop | None = None
_bridge_lock = threading.Lock()


def _ensure_bridge_loop() -> asyncio.AbstractEventLoop:
    """惰性启动常驻后台事件循环（daemon 线程），供同步桥接复用。"""
    global _bridge_loop
    if _bridge_loop is not None and _bridge_loop.is_running():
        return _bridge_loop
    with _bridge_lock:
        if _bridge_loop is not None and _bridge_loop.is_running():
            return _bridge_loop
        loop = asyncio.new_event_loop()
        threading.Thread(
            target=loop.run_forever, name="db-bridge-loop", daemon=True
        ).start()
        _bridge_loop = loop
        return loop


def run_async(coro):
    """在同步上下文中运行异步协程，自动处理事件循环桥接。

    - 无运行中循环（脚本/CLI）→ asyncio.run 直接执行
    - 有运行中循环（uvicorn 请求上下文内的同步调用）→ 提交到常驻桥接循环，
      协程内按当前循环取 engine，避免 asyncpg 跨循环错误（uvloop 同样适用）
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    loop = _ensure_bridge_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()
