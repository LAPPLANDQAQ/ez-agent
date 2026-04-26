"""Redis cache and live event bus helpers with in-process fallbacks."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
import time
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

_redis_client: Redis | None = None
_memory_cache: dict[str, tuple[float, str]] = {}
_subscribers: dict[str, set[asyncio.Queue[dict]]] = {}


def _event_channel(session_id: str) -> str:
    """Build a Redis pub/sub channel name for a research session."""
    return f"research_events:{session_id}"


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
    """Publish a live event through Redis pub/sub with memory fallback."""
    try:
        await _get_redis().publish(
            _event_channel(session_id),
            json.dumps(event, ensure_ascii=False),
        )
    except Exception as exc:
        from app.infra.logger import logger

        logger.warning("Redis publish failed; using memory fallback | error={}", exc)

    queues = list(_subscribers.get(session_id, set()))
    for queue in queues:
        await queue.put(event)


def _memory_subscribe(session_id: str) -> AsyncIterator[dict]:
    """Subscribe to live events through an in-process queue."""
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


async def subscribe(session_id: str) -> AsyncIterator[dict]:
    """Subscribe to live events for one session without replaying history."""
    channel = _event_channel(session_id)
    try:
        pubsub = _get_redis().pubsub()
        await pubsub.subscribe(channel)
    except Exception as exc:
        from app.infra.logger import logger

        logger.warning("Redis subscribe failed; using memory fallback | error={}", exc)
        return _memory_subscribe(session_id)

    async def iterator() -> AsyncIterator[dict]:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                if isinstance(data, dict):
                    yield data
                else:
                    yield json.loads(str(data))
        finally:
            await pubsub.unsubscribe(channel)
            close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    return iterator()
