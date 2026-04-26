import asyncio
import json

import pytest

from app.api.routes import list_routes
from app.api.sse import event_generator
from app.infra.cache import publish, subscribe


def test_list_routes_contains_health() -> None:
    assert "/health" in list_routes()


@pytest.mark.asyncio
async def test_publish_delivers_live_events_to_subscribers() -> None:
    """publish should deliver live events to active subscribers only."""
    events = await subscribe("session-live")

    await publish("session-live", {"event_id": 1, "type": "stage", "stage": "x"})

    event = await asyncio.wait_for(events.__anext__(), timeout=1)
    assert event == {"event_id": 1, "type": "stage", "stage": "x"}


@pytest.mark.asyncio
async def test_event_generator_replays_history_then_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """event_generator should subscribe first, replay history, then stream live."""
    history_calls: list[dict] = []

    async def fake_list_events(
        session_id: str,
        *,
        after_event_id: int = 0,
    ) -> list[dict]:
        history_calls.append(
            {"session_id": session_id, "after_event_id": after_event_id}
        )
        await publish(
            session_id,
            {"event_id": 2, "type": "stage", "stage": "live-before-history"},
        )
        return [{"event_id": 1, "type": "stage", "stage": "history"}]

    monkeypatch.setattr("app.api.sse._list_events", fake_list_events)

    events = event_generator("session-stream")
    first = await asyncio.wait_for(events.__anext__(), timeout=1)
    second = await asyncio.wait_for(events.__anext__(), timeout=1)

    assert history_calls == [{"session_id": "session-stream", "after_event_id": 0}]
    assert first["event"] == "stage"
    assert first["id"] == "1"
    assert json.loads(first["data"])["stage"] == "history"
    assert second["id"] == "2"
    assert json.loads(second["data"])["stage"] == "live-before-history"


@pytest.mark.asyncio
async def test_event_generator_skips_duplicate_live_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live events at or before the last history cursor should be skipped."""

    async def fake_list_events(
        session_id: str,
        *,
        after_event_id: int = 0,
    ) -> list[dict]:
        await publish(session_id, {"event_id": 1, "type": "stage", "stage": "dupe"})
        await publish(session_id, {"event_id": 2, "type": "stage", "stage": "new"})
        return [{"event_id": 1, "type": "stage", "stage": "history"}]

    monkeypatch.setattr("app.api.sse._list_events", fake_list_events)

    events = event_generator("session-dedupe")
    first = await asyncio.wait_for(events.__anext__(), timeout=1)
    second = await asyncio.wait_for(events.__anext__(), timeout=1)

    assert json.loads(first["data"])["stage"] == "history"
    assert json.loads(second["data"])["stage"] == "new"
