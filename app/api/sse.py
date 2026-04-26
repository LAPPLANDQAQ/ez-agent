"""SSE event generation for research sessions."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.infra.cache import subscribe


def _event_id(event: dict) -> int:
    """Return the monotonic event cursor from a persisted event."""
    raw_event_id = event.get("event_id", event.get("id", 0))
    if isinstance(raw_event_id, int):
        return raw_event_id
    try:
        return int(raw_event_id)
    except (TypeError, ValueError):
        return 0


def _event_type(event: dict) -> str:
    """Return the SSE event name for an event payload."""
    raw_type = event.get("type", event.get("event_type", "message"))
    return str(raw_type)


def _event_payload(event: dict) -> dict:
    """Build the JSON payload sent as SSE data."""
    payload = dict(event)
    payload.setdefault("event_id", _event_id(event))
    return payload


def to_sse_event(event: dict) -> dict:
    """Convert a stored or live event into EventSourceResponse format."""
    event_id = _event_id(event)
    return {
        "event": _event_type(event),
        "id": str(event_id),
        "data": json.dumps(_event_payload(event), ensure_ascii=False),
    }


async def _list_events(session_id: str, *, after_event_id: int) -> list[dict]:
    """Load historical events from the database layer when available."""
    from app.infra.db import list_events

    return await list_events(session_id, after_event_id=after_event_id)


async def event_generator(
    session_id: str,
    *,
    after_event_id: int = 0,
) -> AsyncIterator[dict]:
    """Yield historical events followed by de-duplicated live events."""
    last_sent_event_id = after_event_id
    live_events = await subscribe(session_id)

    history = await _list_events(session_id, after_event_id=last_sent_event_id)
    for event in history:
        event_id = _event_id(event)
        if event_id <= last_sent_event_id:
            continue
        last_sent_event_id = event_id
        yield to_sse_event(event)

    async for event in live_events:
        event_id = _event_id(event)
        if event_id <= last_sent_event_id:
            continue
        last_sent_event_id = event_id
        yield to_sse_event(event)
