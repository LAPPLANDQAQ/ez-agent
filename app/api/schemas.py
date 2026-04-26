"""Pydantic schemas for the research API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    """Request body for creating a research session."""

    query: str = Field(..., min_length=5, max_length=500)
    max_iterations: int = Field(default=3, ge=1, le=5)
    language: Literal["zh", "en"] = "zh"


class ResearchResponse(BaseModel):
    """Response returned after a session is created."""

    session_id: str
    status: Literal["created"]
    stream_url: str
    created_at: str


class SessionSummary(BaseModel):
    """Compact session representation for listings."""

    session_id: str
    query: str
    status: Literal["created", "running", "done", "failed", "timeout"]
    requested_language: Literal["zh", "en"]
    max_iterations: int
    total_tokens: int
    iteration_count: int
    created_at: str
    updated_at: str


class SessionDetail(SessionSummary):
    """Detailed session representation."""

    final_report: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


class ErrorResponse(BaseModel):
    """Standard API error response."""

    code: str
    message: str
