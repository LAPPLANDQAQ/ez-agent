"""Unified research execution entry points."""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Literal
from uuid import uuid4

from app.config import get_settings
from app.core.graph import build_graph
from app.core.state import ResearchState
from app.domain.models import EmitFn
from app.infra.db import save_citations, update_session
from app.infra.logger import logger


def _initial_state(
    session_id: str,
    *,
    query: str,
    requested_language: Literal["zh", "en"],
    max_iterations: int,
) -> ResearchState:
    """Build the complete initial graph state."""
    return {
        "session_id": session_id,
        "original_query": query,
        "requested_language": requested_language,
        "max_iterations": max_iterations,
        "sub_questions": [],
        "search_results": [],
        "latest_search_results": [],
        "read_chunks": [],
        "latest_read_chunks": [],
        "critic_decision": None,
        "final_report": None,
        "citations": [],
        "iteration": 0,
        "total_tokens": 0,
        "status": "running",
    }


def _error_mapping(exc: BaseException) -> tuple[str, str, Literal["failed", "timeout"]]:
    """Map execution exceptions to public error codes and DB statuses."""
    if isinstance(exc, asyncio.TimeoutError):
        return "E4002", "Research session timed out", "timeout"
    if isinstance(exc, RuntimeError):
        return "E2001", "All LLM models failed", "failed"
    if isinstance(exc, ValueError):
        return "E2002", "LLM returned invalid JSON", "failed"

    message = str(exc).lower()
    if "search" in message:
        return "E3001", "Search provider failed", "failed"
    if "fetch" in message or "read" in message:
        return "E3002", "Web fetch failed", "failed"
    return "E5001", "Unknown research error", "failed"


def _finish_reason(state: ResearchState) -> str:
    """Return the normal completion reason for a finished state."""
    settings = get_settings()
    if state["total_tokens"] >= settings.TOKEN_BUDGET:
        return "token_budget_exceeded"
    if state["iteration"] >= state["max_iterations"]:
        return "max_iterations_reached"
    if state["critic_decision"] and state["critic_decision"].sufficient:
        return "sufficient"
    return "completed"


async def run_research_session(
    session_id: str,
    *,
    query: str,
    requested_language: Literal["zh", "en"],
    max_iterations: int,
    emit_fn: EmitFn,
) -> None:
    """Run one persisted research session and map final state to DB/events."""
    started_at = monotonic()
    initial_state = _initial_state(
        session_id,
        query=query,
        requested_language=requested_language,
        max_iterations=max_iterations,
    )
    graph = build_graph(emit_fn=emit_fn)
    settings = get_settings()

    try:
        state = await asyncio.wait_for(
            graph.ainvoke(initial_state),
            timeout=settings.RESEARCH_TIMEOUT_SECONDS,
        )
        duration_ms = int((monotonic() - started_at) * 1000)
        citations = [citation.model_dump() for citation in state["citations"]]
        await save_citations(session_id, citations)
        await update_session(
            session_id,
            status=state["status"],
            final_report=state["final_report"],
            total_tokens=state["total_tokens"],
            iteration_count=state["iteration"],
            duration_ms=duration_ms,
            error_message=None,
        )
        await emit_fn(
            {
                "type": "done",
                "report": state["final_report"],
                "citations": citations,
                "stats": {
                    "total_tokens": state["total_tokens"],
                    "iterations": state["iteration"],
                    "duration_ms": duration_ms,
                    "finish_reason": _finish_reason(state),
                },
            }
        )
    except Exception as exc:
        code, message, status = _error_mapping(exc)
        logger.exception("Research session failed | session_id={} code={}", session_id, code)
        duration_ms = int((monotonic() - started_at) * 1000)
        await update_session(
            session_id,
            status=status,
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        await emit_fn({"type": "error", "code": code, "message": message})


async def run_research_cli(
    *,
    query: str,
    requested_language: Literal["zh", "en"] = "zh",
    max_iterations: int = 3,
    emit_fn: EmitFn | None = None,
) -> dict:
    """Run the research graph for CLI callers and return the final state."""

    async def default_emit(event: dict) -> None:
        logger.info("[{}] {}", event.get("type", "?"), event)

    graph = build_graph(emit_fn=emit_fn or default_emit)
    return await graph.ainvoke(
        _initial_state(
            str(uuid4()),
            query=query,
            requested_language=requested_language,
            max_iterations=max_iterations,
        )
    )
