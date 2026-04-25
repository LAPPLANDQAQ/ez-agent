"""Commit #2 tests for the LLM client."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from app.domain.models import LLMResult, SearchResult
from app.tools.llm import call_llm
from app.tools.search import search_multiple


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


def _search_response(*items: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build a Tavily-like search response."""
    return {"results": list(items)}


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


@pytest.mark.asyncio
async def test_search_multiple_returns_normalized_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_multiple should call Tavily and normalize search results."""
    calls: list[dict[str, Any]] = []

    class FakeAsyncTavilyClient:
        """Successful fake Tavily client."""

        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

        async def search(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
            calls.append({"api_key": self.api_key, **kwargs})
            return _search_response(
                {
                    "url": "https://example.com/a",
                    "title": "Example A",
                    "content": "Snippet A",
                    "score": 0.91,
                }
            )

        async def close(self) -> None:
            calls.append({"closed": True})

    monkeypatch.setattr("app.tools.search.AsyncTavilyClient", FakeAsyncTavilyClient)
    with patch.dict(os.environ, _required_env(), clear=False):
        results = await search_multiple(["agent search"], top_k=3)

    assert results == [
        SearchResult(
            url="https://example.com/a",
            title="Example A",
            snippet="Snippet A",
            score=0.91,
            sub_question_index=0,
        )
    ]
    assert calls[0] == {
        "api_key": "tvly-test",
        "query": "agent search",
        "max_results": 3,
    }
    assert calls[-1] == {"closed": True}


@pytest.mark.asyncio
async def test_search_multiple_deduplicates_urls_across_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate URLs across queries should be kept only once."""

    class FakeAsyncTavilyClient:
        """Fake Tavily client returning overlapping URLs."""

        def __init__(self, *, api_key: str) -> None:
            pass

        async def search(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
            query = kwargs["query"]
            if query == "first":
                return _search_response(
                    {
                        "url": "https://example.com/shared",
                        "title": "Shared first",
                        "content": "First snippet",
                        "score": 0.7,
                    },
                    {
                        "url": "https://example.com/unique",
                        "title": "Unique",
                        "content": "Unique snippet",
                        "score": 0.6,
                    },
                )
            return _search_response(
                {
                    "url": "https://example.com/shared",
                    "title": "Shared second",
                    "content": "Second snippet",
                    "score": 0.9,
                }
            )

    monkeypatch.setattr("app.tools.search.AsyncTavilyClient", FakeAsyncTavilyClient)
    with patch.dict(os.environ, _required_env(), clear=False):
        results = await search_multiple(["first", "second"])

    assert [result.url for result in results] == [
        "https://example.com/shared",
        "https://example.com/unique",
    ]
    assert [result.sub_question_index for result in results] == [0, 0]


@pytest.mark.asyncio
async def test_search_multiple_keeps_successful_queries_when_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single query failure should not fail the whole batch."""

    class FakeAsyncTavilyClient:
        """Fake Tavily client with one failing query."""

        def __init__(self, *, api_key: str) -> None:
            pass

        async def search(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
            if kwargs["query"] == "bad":
                raise TimeoutError("search timeout")
            return _search_response(
                {
                    "url": "https://example.com/good",
                    "title": "Good",
                    "snippet": "Good snippet",
                    "score": 1.0,
                }
            )

    monkeypatch.setattr("app.tools.search.AsyncTavilyClient", FakeAsyncTavilyClient)
    with patch.dict(os.environ, _required_env(), clear=False):
        results = await search_multiple(["bad", "good"])

    assert len(results) == 1
    assert results[0].url == "https://example.com/good"
    assert results[0].sub_question_index == 1


@pytest.mark.asyncio
async def test_search_multiple_ignores_blank_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank queries should be ignored without calling Tavily."""
    called = False

    class FakeAsyncTavilyClient:
        """Fake Tavily client that should not be instantiated."""

        def __init__(self, *, api_key: str) -> None:
            nonlocal called
            called = True

    monkeypatch.setattr("app.tools.search.AsyncTavilyClient", FakeAsyncTavilyClient)

    results = await search_multiple(["", "   "])

    assert results == []
    assert called is False
