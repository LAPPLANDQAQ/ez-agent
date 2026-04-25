"""Commit #2 tests for the LLM client."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from app.domain.models import LLMResult
from app.tools.llm import call_llm


class FakeResponse:
    """Small response object that mimics LangChain chat model responses."""

    def __init__(
        self,
        content: str,
        *,
        usage_metadata: dict[str, int] | None = None,
        response_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.usage_metadata = usage_metadata or {}
        self.response_metadata = response_metadata or {}


def _required_env(model: str = "deepseek-chat") -> dict[str, str]:
    """Return the minimum environment needed to instantiate settings."""
    return {
        "DEEPSEEK_API_KEY": "sk-test",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.test/v1",
        "DEEPSEEK_MODEL": model,
        "TAVILY_API_KEY": "tvly-test",
    }


@pytest.mark.asyncio
async def test_call_llm_returns_normalized_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_llm should return the shared LLMResult model."""
    calls: list[dict[str, Any]] = []

    class FakeChatOpenAI:
        """Successful fake ChatOpenAI client."""

        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

        async def ainvoke(self, messages: list[dict]) -> FakeResponse:
            assert messages == [{"role": "user", "content": "hello"}]
            return FakeResponse("ok", usage_metadata={"total_tokens": 12})

    monkeypatch.setattr("app.tools.llm.ChatOpenAI", FakeChatOpenAI)
    with patch.dict(os.environ, _required_env(), clear=False):
        result = await call_llm([{"role": "user", "content": "hello"}])

    assert isinstance(result, LLMResult)
    assert result.text == "ok"
    assert result.total_tokens == 12
    assert result.model_name == "deepseek-chat"
    assert result.provider == "deepseek"
    assert calls[0]["api_key"] == "sk-test"
    assert calls[0]["base_url"] == "https://api.deepseek.test/v1"
    assert calls[0]["temperature"] == 0.3
    assert calls[0]["max_tokens"] == 4096


@pytest.mark.asyncio
async def test_call_llm_passes_json_response_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON mode should pass OpenAI-compatible response_format."""
    calls: list[dict[str, Any]] = []

    class FakeChatOpenAI:
        """Fake client for inspecting initialization kwargs."""

        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

        async def ainvoke(self, messages: list[dict]) -> FakeResponse:
            return FakeResponse('{"ok": true}', usage_metadata={"total_tokens": 3})

    monkeypatch.setattr("app.tools.llm.ChatOpenAI", FakeChatOpenAI)
    with patch.dict(os.environ, _required_env(), clear=False):
        await call_llm(
            [{"role": "user", "content": "json"}],
            json_mode=True,
            temperature=0.1,
            max_tokens=128,
        )

    assert calls[0]["model_kwargs"] == {
        "response_format": {"type": "json_object"},
    }
    assert calls[0]["temperature"] == 0.1
    assert calls[0]["max_tokens"] == 128


@pytest.mark.asyncio
async def test_call_llm_retries_then_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client should retry a failed model three times before fallback."""
    attempts: list[str] = []

    class FakeChatOpenAI:
        """Fake client that fails for the primary model."""

        def __init__(self, **kwargs: Any) -> None:
            self.model = kwargs["model"]

        async def ainvoke(self, messages: list[dict]) -> FakeResponse:
            attempts.append(self.model)
            if self.model == "primary-model":
                raise TimeoutError("primary unavailable")
            return FakeResponse("fallback ok", usage_metadata={"total_tokens": 9})

    monkeypatch.setattr("app.tools.llm.ChatOpenAI", FakeChatOpenAI)
    with patch.dict(os.environ, _required_env(model="primary-model"), clear=False):
        result = await call_llm([{"role": "user", "content": "hello"}])

    assert attempts == [
        "primary-model",
        "primary-model",
        "primary-model",
        "deepseek-reasoner",
    ]
    assert result.text == "fallback ok"
    assert result.model_name == "deepseek-reasoner"
    assert result.total_tokens == 9


@pytest.mark.asyncio
async def test_call_llm_defaults_missing_token_usage_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing token metadata should not break callers."""

    class FakeChatOpenAI:
        """Fake client that omits usage metadata."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        async def ainvoke(self, messages: list[dict]) -> FakeResponse:
            return FakeResponse("no usage")

    monkeypatch.setattr("app.tools.llm.ChatOpenAI", FakeChatOpenAI)
    with patch.dict(os.environ, _required_env(), clear=False):
        result = await call_llm([{"role": "user", "content": "hello"}])

    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_call_llm_raises_when_all_models_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All provider failures should map to the frozen RuntimeError contract."""
    attempts: list[str] = []

    class FakeChatOpenAI:
        """Fake client that always fails."""

        def __init__(self, **kwargs: Any) -> None:
            self.model = kwargs["model"]

        async def ainvoke(self, messages: list[dict]) -> FakeResponse:
            attempts.append(self.model)
            raise ConnectionError("down")

    monkeypatch.setattr("app.tools.llm.ChatOpenAI", FakeChatOpenAI)
    with patch.dict(os.environ, _required_env(model="primary-model"), clear=False):
        with pytest.raises(RuntimeError, match="All LLM models failed"):
            await call_llm([{"role": "user", "content": "hello"}])

    assert attempts == [
        "primary-model",
        "primary-model",
        "primary-model",
        "deepseek-reasoner",
        "deepseek-reasoner",
        "deepseek-reasoner",
    ]
