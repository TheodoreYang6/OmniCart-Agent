"""缓存工具层 — get-or-compute 模式 + 批量失效 + 指标统计

所有缓存操作透明降级：Redis 不可用时自动跳过，不抛异常。
"""

import hashlib
import json
import logging
import time
import functools
from typing import Any, Callable, Awaitable, Optional

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

# 轻量命中率统计
_stats = {"hits": 0, "misses": 0}


def get_stats() -> dict:
    """返回缓存命中率统计"""
    total = _stats["hits"] + _stats["misses"]
    return {
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "hit_rate": round(_stats["hits"] / total, 3) if total > 0 else 0.0,
    }


def make_key(prefix: str, *parts: str) -> str:
    """生成缓存键：omnicart:{prefix}:{md5(parts...)}"""
    raw = "|".join(str(p) for p in parts if p)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
    return f"omnicart:{prefix}:{digest}"


async def cached(
    key: str,
    ttl: int,
    factory: Callable[[], Awaitable[Any]],
    serializer: Optional[Callable[[Any], str]] = None,
    deserializer: Optional[Callable[[str], Any]] = None,
) -> Any:
    """get-or-compute：命中 Redis 则直接返回，否则调用 factory 并缓存。

    Args:
        key: 缓存键
        ttl: 过期时间（秒）
        factory: 异步工厂函数，仅在 miss 时调用
        serializer: 自定义序列化（默认 json.dumps）
        deserializer: 自定义反序列化（默认 json.loads）

    Returns:
        factory 的返回值（来自缓存或新计算）
    """
    redis = await get_redis()
    if redis is None:
        return await factory()

    try:
        raw = await redis.get(key)
        if raw is not None:
            _stats["hits"] += 1
            logger.debug(f"Cache HIT: {key}")
            if deserializer:
                return deserializer(raw)
            return json.loads(raw)
    except Exception:
        pass  # 读取失败视为 miss

    _stats["misses"] += 1
    logger.debug(f"Cache MISS: {key}")
    result = await factory()

    try:
        _serialize = serializer or (lambda v: json.dumps(v, ensure_ascii=False, default=str))
        await redis.setex(key, ttl, _serialize(result))
    except Exception as e:
        logger.debug(f"Cache write failed: {e}")

    return result


async def invalidate(pattern: str) -> int:
    """按模式批量删除缓存键。返回删除数量。"""
    redis = await get_redis()
    if redis is None:
        return 0
    try:
        keys = []
        async for k in redis.scan_iter(match=pattern, count=100):
            keys.append(k)
        if keys:
            return await redis.delete(*keys)
    except Exception as e:
        logger.debug(f"Cache invalidate failed: {e}")
    return 0


async def cache_set(key: str, value: Any, ttl: int) -> bool:
    """直接写入缓存"""
    redis = await get_redis()
    if redis is None:
        return False
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
        await redis.setex(key, ttl, raw)
        return True
    except Exception:
        return False


async def cache_get(key: str) -> Optional[Any]:
    """直接读取缓存"""
    redis = await get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_result(
    prefix: str,
    ttl: int,
    *,
    serializer: Optional[Callable[[Any], str]] = None,
    deserializer: Optional[Callable[[str], Any]] = None,
):
    """装饰器版 get-or-compute（spec §七）：按 prefix + 参数生成缓存键。

    统一四级 TTL 缓存的声明式写法，Key 规范集中在本文件。示例::

        @cache_result("semantic_search", REDIS_CACHE_TTL_SEARCH)
        async def search(query: str, top_k: int) -> list[dict]: ...
    """

    def _decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            key = make_key(prefix, *parts)
            return await cached(
                key, ttl, lambda: fn(*args, **kwargs),
                serializer=serializer, deserializer=deserializer,
            )

        return _wrapped

    return _decorator
