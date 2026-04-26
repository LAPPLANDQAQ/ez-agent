"""FastAPI routes for the research API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import ResearchRequest, ResearchResponse, SessionDetail, SessionSummary
from app.api.sse import event_generator
from app.config import get_settings
from app.core.runner import run_research_session
from app.infra.cache import publish
from app.infra.db import (
    claim_session_start,
    create_session,
    get_session,
    list_sessions,
    save_single_event,
)

router = APIRouter(prefix="/api/v1")


def list_routes() -> list[str]:
    """Return public route paths for simple health tests."""
    return ["/health", "/api/v1/research", "/api/v1/research/stream/{session_id}"]


def _forget_task(tasks: dict[str, asyncio.Task], session_id: str) -> None:
    """Remove a completed research task from the app-level registry."""
    tasks.pop(session_id, None)


@router.get("/health")
async def health() -> dict[str, str]:
    """Return API health status."""
    return {"status": "ok"}


@router.post("/research", response_model=ResearchResponse)
async def create_research(request: ResearchRequest) -> ResearchResponse:
    """Create a research session without starting graph execution."""
    settings = get_settings()
    max_iterations = min(request.max_iterations, settings.MAX_ITERATIONS)
    session_id = await create_session(
        request.query,
        requested_language=request.language,
        max_iterations=max_iterations,
    )
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=500, detail="Session was not created")
    return ResearchResponse(
        session_id=session_id,
        status="created",
        stream_url=f"/api/v1/research/stream/{session_id}",
        created_at=session["created_at"],
    )


@router.get("/research", response_model=list[SessionSummary])
async def list_research_sessions(limit: int = 20) -> list[dict]:
    """List recent research sessions."""
    return await list_sessions(limit=limit)


@router.get("/research/{session_id}", response_model=SessionDetail)
async def get_research_session(session_id: str) -> dict:
    """Return session details."""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/research/stream/{session_id}")
async def stream_research_session(
    request: Request,
    session_id: str,
    after_event_id: int = 0,
) -> EventSourceResponse:
    """Stream a research session, starting it only on the first connection."""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    started = await claim_session_start(session_id)
    if started:

        async def api_emit(event: dict) -> None:
            persisted = await save_single_event(session_id, event)
            await publish(session_id, persisted)

        task = asyncio.create_task(
            run_research_session(
                session_id,
                query=session["query"],
                requested_language=session["requested_language"],
                max_iterations=session["max_iterations"],
                emit_fn=api_emit,
            )
        )
        request.app.state.research_tasks[session_id] = task
        task.add_done_callback(
            lambda _task: _forget_task(request.app.state.research_tasks, session_id)
        )

    return EventSourceResponse(
        event_generator(session_id, after_event_id=after_event_id)
    )
