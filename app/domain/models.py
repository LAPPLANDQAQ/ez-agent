"""Shared domain models.

This module must not import other application modules.
"""

from pydantic import BaseModel


class LLMResult(BaseModel):
    """Normalized result returned by an LLM provider."""

    text: str
    total_tokens: int = 0
    model_name: str = ""
    provider: str = ""


class SearchResult(BaseModel):
    """Normalized result returned by a search provider."""

    url: str
    title: str
    snippet: str
    score: float = 0.0
    sub_question_index: int = 0


class FetchTarget(BaseModel):
    """Single URL selected for fetching and reading."""

    url: str
    title: str
    source_id: int


class ReadChunk(BaseModel):
    """Summarized content extracted from a fetched source."""

    source_id: int
    url: str
    title: str
    summary: str
    raw_length: int = 0
