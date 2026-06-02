import json
from typing import Any

from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get_json(key: str) -> Any | None:
    raw = await get_redis().get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)


async def cache_invalidate_prefix(prefix: str) -> int:
    redis = get_redis()
    deleted = 0
    async for key in redis.scan_iter(match=f"{prefix}*", count=200):
        await redis.delete(key)
        deleted += 1
    return deleted
