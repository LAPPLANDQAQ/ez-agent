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
