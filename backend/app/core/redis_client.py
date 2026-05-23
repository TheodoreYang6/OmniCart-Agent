"""Redis 连接管理器 — 异步连接池 + 健康检查 + 生命周期管理"""

import logging
from typing import Optional

import redis.asyncio as redis

from app.core.config import REDIS_URL, USE_REDIS

logger = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


async def get_redis() -> Optional[redis.Redis]:
    """获取 Redis 客户端（若未初始化则自动连接）"""
    global _client
    if not USE_REDIS:
        return None
    if _client is None:
        try:
            _client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await _client.ping()
            logger.info(f"Redis connected: {REDIS_URL}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — cache disabled")
            _client = None
    return _client


async def init_redis() -> None:
    """应用启动时初始化 Redis 连接"""
    await get_redis()


async def close_redis() -> None:
    """应用关闭时释放 Redis 连接"""
    global _client
    if _client:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
        logger.info("Redis connection closed")


def health_check() -> bool:
    """同步健康检查（不强制连接）"""
    return _client is not None and USE_REDIS
