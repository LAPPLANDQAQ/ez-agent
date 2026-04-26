"""Tests for API, database, runner, and SSE behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import list_routes, stream_research_session
from app.api.sse import event_generator
from app.domain.models import Citation, CriticDecision
from app.infra.cache import publish, subscribe
from app.infra.db import (
    claim_session_start,
    create_session,
    get_session,
    init_db,
    list_events,
    save_single_event,
)
from app.main import app


@pytest.fixture
def api_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure an isolated API test environment."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("MAX_ITERATIONS", "3")
    monkeypatch.setenv("TOKEN_BUDGET", "100000")
    monkeypatch.setenv("RESEARCH_TIMEOUT_SECONDS", "5")

    import app.infra.db as db_module

    db_module._engine = None
    db_module._session_factory = None


def test_list_routes_contains_health() -> None:
    """Route listing should keep the health endpoint visible."""
    assert "/health" in list_routes()


@pytest.mark.asyncio
async def test_database_session_lifecycle(api_env: None) -> None:
    """DB helpers should create, claim, update, and replay session events."""
    await init_db()
    session_id = await create_session(
        "How do research agents validate sources?",
        requested_language="en",
        max_iterations=2,
    )

    session = await get_session(session_id)
    assert session is not None
    assert session["status"] == "created"
    assert session["requested_language"] == "en"

    assert await claim_session_start(session_id) is True
    assert await claim_session_start(session_id) is False

    event = await save_single_event(
        session_id,
        {"type": "stage", "stage": "planning", "message": "Planning"},
    )
    assert event["event_id"] == 1
    assert event["type"] == "stage"

    events = await list_events(session_id, after_event_id=0)
    assert [item["event_id"] for item in events] == [1]


def test_create_research_endpoint_returns_created(api_env: None) -> None:
    """POST /research should create but not start a session."""
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research",
            json={
                "query": "How do research agents validate web sources?",
                "language": "en",
                "max_iterations": 2,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "created"
    assert payload["stream_url"].endswith(payload["session_id"])


@pytest.mark.asyncio
async def test_stream_endpoint_claims_and_starts_once(
    api_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First stream connection should atomically claim and schedule graph work."""
    await init_db()
    session_id = await create_session(
        "How do research agents validate web sources?",
        requested_language="zh",
        max_iterations=3,
    )
    started: list[dict] = []

    async def fake_run_research_session(*args, **kwargs) -> None:
        started.append({"args": args, **kwargs})

    monkeypatch.setattr("app.api.routes.run_research_session", fake_run_research_session)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(research_tasks={})))

    response = await stream_research_session(request, session_id)
    second_response = await stream_research_session(request, session_id)
    await asyncio.gather(*request.app.state.research_tasks.values())

    session = await get_session(session_id)
    assert response.status_code == 200
    assert second_response.status_code == 200
    assert session is not None
    assert session["status"] == "running"
    assert len(started) == 1
    assert started[0]["requested_language"] == "zh"


@pytest.mark.asyncio
async def test_publish_delivers_live_events_to_subscribers() -> None:
    """publish should deliver live events to active subscribers only."""
    events = await subscribe("session-live")

    await publish("session-live", {"event_id": 1, "type": "stage", "stage": "x"})

    event = await asyncio.wait_for(events.__anext__(), timeout=1)
    assert event == {"event_id": 1, "type": "stage", "stage": "x"}
    await events.aclose()


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
    await events.aclose()


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
    await events.aclose()


@pytest.mark.asyncio
async def test_runner_success_updates_db_and_emits_done(
    api_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_research_session should persist final state and emit done."""
    from app.core.runner import run_research_session

    await init_db()
    session_id = await create_session(
        "How do research agents validate web sources?",
        requested_language="en",
        max_iterations=2,
    )
    await claim_session_start(session_id)
    events: list[dict] = []

    class FakeGraph:
        async def ainvoke(self, state: dict) -> dict:
            return {
                **state,
                "final_report": "Final [1]",
                "citations": [
                    Citation(
                        source_id=1,
                        url="https://example.com",
                        title="Example",
                        used_in_report=True,
                    )
                ],
                "critic_decision": CriticDecision(sufficient=True),
                "total_tokens": 12,
                "status": "done",
            }

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.runner.build_graph", lambda emit_fn=None: FakeGraph())

    await run_research_session(
        session_id,
        query="How do research agents validate web sources?",
        requested_language="en",
        max_iterations=2,
        emit_fn=emit,
    )

    session = await get_session(session_id)
    assert session is not None
    assert session["status"] == "done"
    assert session["final_report"] == "Final [1]"
    assert events[-1]["type"] == "done"
    assert events[-1]["stats"]["finish_reason"] == "sufficient"


@pytest.mark.asyncio
async def test_runner_failure_maps_errors(
    api_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_research_session should map failures to error events and DB status."""
    from app.core.runner import run_research_session

    await init_db()
    session_id = await create_session(
        "How do research agents validate web sources?",
        requested_language="en",
        max_iterations=2,
    )
    await claim_session_start(session_id)
    events: list[dict] = []

    class FakeGraph:
        async def ainvoke(self, state: dict) -> dict:
            raise ValueError("bad json")

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.runner.build_graph", lambda emit_fn=None: FakeGraph())

    await run_research_session(
        session_id,
        query="How do research agents validate web sources?",
        requested_language="en",
        max_iterations=2,
        emit_fn=emit,
    )

    session = await get_session(session_id)
    assert session is not None
    assert session["status"] == "failed"
    assert events[-1] == {
        "type": "error",
        "code": "E2002",
        "message": "LLM returned invalid JSON",
    }
