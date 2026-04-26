"""Redis cache and live event bus helpers with in-process fallbacks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import time
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

_redis_client: Redis | None = None
_memory_cache: dict[str, tuple[float, str]] = {}
_subscribers: dict[str, set[asyncio.Queue[dict]]] = {}


def _memory_get(key: str) -> str | None:
    """Read a value from the local fallback cache."""
    cached = _memory_cache.get(key)
    if cached is None:
        return None

    expires_at, value = cached
    if expires_at <= time.monotonic():
        _memory_cache.pop(key, None)
        return None
    return value


def _memory_setex(key: str, ttl: int, value: str) -> None:
    """Write a value to the local fallback cache."""
    _memory_cache[key] = (time.monotonic() + ttl, value)


def _decode_cache_value(value: Any) -> str | None:
    """Decode a Redis value into a string."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _get_redis() -> Redis:
    """Return a lazily initialized Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def cache_get(key: str) -> str | None:
    """Get a cached string value by key."""
    try:
        value = await _get_redis().get(key)
    except Exception as exc:
        from app.infra.logger import logger

        logger.warning("Redis cache get failed; using memory fallback | error={}", exc)
        return _memory_get(key)

    return _decode_cache_value(value)


async def cache_setex(key: str, ttl: int, value: str) -> None:
    """Set a cached string value with a TTL in seconds."""
    try:
        await _get_redis().setex(key, ttl, value)
    except Exception as exc:
        from app.infra.logger import logger

        logger.warning("Redis cache set failed; using memory fallback | error={}", exc)
        _memory_setex(key, ttl, value)


async def publish(session_id: str, event: dict) -> None:
    """Publish a live event to local subscribers for one research session."""
    queues = list(_subscribers.get(session_id, set()))
    for queue in queues:
        await queue.put(event)


async def subscribe(session_id: str) -> AsyncIterator[dict]:
    """Subscribe to live events for one session without replaying history."""
    queue: asyncio.Queue[dict] = asyncio.Queue()
    subscribers = _subscribers.setdefault(session_id, set())
    subscribers.add(queue)

    async def iterator() -> AsyncIterator[dict]:
        try:
            while True:
                yield await queue.get()
        finally:
            subscribers.discard(queue)
            if not subscribers:
                _subscribers.pop(session_id, None)

    return iterator()
