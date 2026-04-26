"""LLM client with retry and model fallback."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.domain.models import LLMResult

_PROVIDER = "deepseek"
_FALLBACK_MODELS = ("deepseek-reasoner",)
_RETRY_COUNT = 3


def _model_names(primary_model: str) -> list[str]:
    """Return primary and fallback model names without duplicates."""
    names = [primary_model, *_FALLBACK_MODELS]
    return list(dict.fromkeys(name for name in names if name))


def _build_client(
    model_name: str,
    *,
    json_mode: bool,
    temperature: float,
    max_tokens: int,
) -> ChatOpenAI:
    """Create a ChatOpenAI client for a single model."""
    settings = get_settings()
    model_kwargs: dict[str, Any] = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}

    client_kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": settings.DEEPSEEK_API_KEY.get_secret_value(),
        "base_url": settings.DEEPSEEK_BASE_URL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "model_kwargs": model_kwargs,
    }
    return ChatOpenAI(**client_kwargs)


def _extract_text(response: Any) -> str:
    """Extract response text from common LangChain response shapes."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def _extract_total_tokens(response: Any) -> int:
    """Extract total token usage, falling back to zero when unavailable."""
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    total_tokens = usage_metadata.get("total_tokens")
    if isinstance(total_tokens, int):
        return total_tokens

    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    total_tokens = token_usage.get("total_tokens")
    if isinstance(total_tokens, int):
        return total_tokens

    from app.infra.logger import logger

    logger.warning("LLM response did not include total token usage; defaulting to 0")
    return 0


async def call_llm(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> LLMResult:
    """Call the configured LLM with retry and fallback model handling."""
    settings = get_settings()
    last_error: Exception | None = None

    for model_name in _model_names(settings.DEEPSEEK_MODEL):
        client = _build_client(
            model_name,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        for attempt in range(1, _RETRY_COUNT + 1):
            try:
                response = await client.ainvoke(messages)
                return LLMResult(
                    text=_extract_text(response),
                    total_tokens=_extract_total_tokens(response),
                    model_name=model_name,
                    provider=_PROVIDER,
                )
            except Exception as exc:
                last_error = exc
                from app.infra.logger import logger

                logger.warning(
                    "LLM call failed | provider={} model={} attempt={}/{} error={}",
                    _PROVIDER,
                    model_name,
                    attempt,
                    _RETRY_COUNT,
                    exc,
                )

    raise RuntimeError("All LLM models failed") from last_error
