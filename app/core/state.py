"""Typed state shared by research graph nodes."""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

from app.domain.models import Citation, CriticDecision, ReadChunk, SearchResult


class ResearchState(TypedDict):
    """LangGraph state for a research session."""

    session_id: str
    original_query: str
    requested_language: Literal["zh", "en"]
    max_iterations: int

    sub_questions: list[str]

    search_results: Annotated[list[SearchResult], add]
    latest_search_results: list[SearchResult]

    read_chunks: Annotated[list[ReadChunk], add]
    latest_read_chunks: list[ReadChunk]

    critic_decision: CriticDecision | None

    final_report: str | None
    citations: list[Citation]

    iteration: int
    total_tokens: int
    status: Literal["running", "done", "failed", "timeout"]
