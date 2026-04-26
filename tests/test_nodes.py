"""Tests for research graph nodes."""

from __future__ import annotations

import pytest

from app.core.nodes import (
    critic_node,
    planner_node,
    reader_node,
    searcher_node,
    writer_node,
)
from app.core.state import ResearchState
from app.domain.models import CriticDecision, LLMResult, ReadChunk, SearchResult


def _initial_state() -> ResearchState:
    """Build a complete initial ResearchState for node tests."""
    return {
        "session_id": "session-1",
        "original_query": "How do research agents validate web sources?",
        "requested_language": "en",
        "max_iterations": 3,
        "sub_questions": [],
        "search_results": [],
        "latest_search_results": [],
        "read_chunks": [],
        "latest_read_chunks": [],
        "critic_decision": None,
        "final_report": None,
        "citations": [],
        "iteration": 0,
        "total_tokens": 5,
        "status": "running",
    }


@pytest.mark.asyncio
async def test_planner_node_returns_sub_questions_and_token_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """planner_node should parse JSON output and accumulate total tokens."""
    calls: list[dict] = []

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        calls.append({"messages": messages, "json_mode": json_mode})
        return LLMResult(
            text='{"sub_questions": ["Find sources", "Compare claims"]}',
            total_tokens=17,
            model_name="fake",
        )

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    result = await planner_node(_initial_state())

    assert result == {
        "sub_questions": ["Find sources", "Compare claims"],
        "total_tokens": 22,
    }
    assert calls[0]["json_mode"] is True
    assert "Research query:" in calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_planner_node_emits_stage_and_sub_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """planner_node should publish planning events when emit_fn is provided."""
    events: list[dict] = []

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        return LLMResult(text='{"questions": ["Question A"]}', total_tokens=1)

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    await planner_node(_initial_state(), emit_fn=emit)

    assert events == [
        {
            "type": "stage",
            "stage": "planning",
            "message": "Planning research sub-questions",
        },
        {"type": "sub_questions", "questions": ["Question A"]},
    ]


@pytest.mark.asyncio
async def test_planner_node_raises_value_error_for_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid planner JSON should raise ValueError for runner mapping."""

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        return LLMResult(text="not json", total_tokens=3)

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    with pytest.raises(ValueError, match="invalid JSON"):
        await planner_node(_initial_state())


@pytest.mark.asyncio
async def test_planner_node_raises_value_error_for_empty_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planner JSON without usable questions should fail fast."""

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        return LLMResult(text='{"sub_questions": []}', total_tokens=3)

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    with pytest.raises(ValueError, match="no sub-questions"):
        await planner_node(_initial_state())


@pytest.mark.asyncio
async def test_searcher_node_uses_sub_questions_on_first_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First search iteration should use planner sub-questions."""
    state = _initial_state()
    state["sub_questions"] = ["first question", "second question"]
    calls: list[list[str]] = []

    async def fake_search_multiple(queries: list[str]) -> list[SearchResult]:
        calls.append(queries)
        return [
            SearchResult(
                url="https://example.com/a",
                title="Example A",
                snippet="Snippet A",
                sub_question_index=0,
            )
        ]

    monkeypatch.setattr("app.core.nodes.search_multiple", fake_search_multiple)

    result = await searcher_node(state)

    assert calls == [["first question", "second question"]]
    assert result["search_results"] == result["latest_search_results"]
    assert result["latest_search_results"][0].url == "https://example.com/a"


@pytest.mark.asyncio
async def test_searcher_node_uses_critic_queries_after_first_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Follow-up search iterations should use critic next_queries."""
    state = _initial_state()
    state["iteration"] = 1
    state["sub_questions"] = ["initial question"]
    state["critic_decision"] = CriticDecision(
        sufficient=False,
        next_queries=["follow-up one", "follow-up two"],
    )
    calls: list[list[str]] = []

    async def fake_search_multiple(queries: list[str]) -> list[SearchResult]:
        calls.append(queries)
        return []

    monkeypatch.setattr("app.core.nodes.search_multiple", fake_search_multiple)

    await searcher_node(state)

    assert calls == [["follow-up one", "follow-up two"]]


@pytest.mark.asyncio
async def test_searcher_node_emits_stage_and_search_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """searcher_node should publish stage and per-query events."""
    state = _initial_state()
    state["sub_questions"] = ["query a"]
    events: list[dict] = []

    async def fake_search_multiple(queries: list[str]) -> list[SearchResult]:
        return []

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.nodes.search_multiple", fake_search_multiple)

    await searcher_node(state, emit_fn=emit)

    assert events == [
        {
            "type": "stage",
            "stage": "searching",
            "message": "Searching for relevant sources",
        },
        {"type": "searching", "query": "query a", "iteration": 0},
    ]


@pytest.mark.asyncio
async def test_reader_node_reads_latest_results_and_accumulates_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reader_node should read only latest results and accumulate total tokens."""
    state = _initial_state()
    state["total_tokens"] = 20
    state["read_chunks"] = [
        ReadChunk(
            source_id=1,
            url="https://example.com/old",
            title="Old",
            summary="Old summary",
        )
    ]
    state["search_results"] = [
        SearchResult(
            url="https://example.com/old-search",
            title="Old Search",
            snippet="Old",
        )
    ]
    state["latest_search_results"] = [
        SearchResult(
            url="https://example.com/a",
            title="Example A",
            snippet="Snippet A",
        ),
        SearchResult(
            url="https://example.com/b",
            title="Example B",
            snippet="Snippet B",
        ),
    ]
    calls: list[dict] = []

    async def fake_fetch_and_summarize_batch(
        targets: list,
        query: str,
    ) -> tuple[list[ReadChunk], int]:
        calls.append({"targets": targets, "query": query})
        return [
            ReadChunk(
                source_id=targets[0].source_id,
                url=targets[0].url,
                title=targets[0].title,
                summary="Summary A",
            )
        ], 13

    monkeypatch.setattr(
        "app.core.nodes.fetch_and_summarize_batch",
        fake_fetch_and_summarize_batch,
    )

    result = await reader_node(state)

    targets = calls[0]["targets"]
    assert calls[0]["query"] == state["original_query"]
    assert [target.url for target in targets] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert [target.source_id for target in targets] == [2, 3]
    assert result["read_chunks"] == result["latest_read_chunks"]
    assert result["latest_read_chunks"][0].source_id == 2
    assert result["total_tokens"] == 33


@pytest.mark.asyncio
async def test_reader_node_emits_stage_and_reading_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reader_node should publish stage and per-target events."""
    state = _initial_state()
    state["latest_search_results"] = [
        SearchResult(
            url="https://example.com/a",
            title="Example A",
            snippet="Snippet A",
        )
    ]
    events: list[dict] = []

    async def fake_fetch_and_summarize_batch(
        targets: list,
        query: str,
    ) -> tuple[list[ReadChunk], int]:
        return [], 0

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr(
        "app.core.nodes.fetch_and_summarize_batch",
        fake_fetch_and_summarize_batch,
    )

    await reader_node(state, emit_fn=emit)

    assert events == [
        {
            "type": "stage",
            "stage": "reading",
            "message": "Reading and summarizing sources",
        },
        {
            "type": "reading",
            "url": "https://example.com/a",
            "title": "Example A",
        },
    ]


@pytest.mark.asyncio
async def test_critic_node_returns_decision_and_accumulates_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """critic_node should parse a decision and accumulate total tokens."""
    state = _initial_state()
    state["total_tokens"] = 30
    state["read_chunks"] = [
        ReadChunk(
            source_id=1,
            url="https://example.com/a",
            title="Example A",
            summary="Useful evidence",
        )
    ]
    calls: list[dict] = []

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        calls.append({"messages": messages, "json_mode": json_mode})
        return LLMResult(
            text=(
                '{"sufficient": true, "missing_aspects": [], '
                '"next_queries": [], "reasoning": "covered"}'
            ),
            total_tokens=11,
        )

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    result = await critic_node(state)

    assert calls[0]["json_mode"] is True
    assert "Source summaries:" in calls[0]["messages"][1]["content"]
    assert result["critic_decision"].sufficient is True
    assert result["total_tokens"] == 41
    assert "iteration" not in result


@pytest.mark.asyncio
async def test_critic_node_truncates_chunks_summary_for_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """critic_node should keep source summaries within the configured limit."""
    state = _initial_state()
    state["read_chunks"] = [
        ReadChunk(
            source_id=1,
            url="https://example.com/a",
            title="Example A",
            summary="a" * 7000,
        )
    ]
    user_contents: list[str] = []

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        user_contents.append(messages[1]["content"])
        return LLMResult(
            text=(
                '{"sufficient": true, "missing_aspects": [], '
                '"next_queries": [], "reasoning": "covered"}'
            ),
            total_tokens=1,
        )

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    await critic_node(state)

    source_summary = user_contents[0].split("Source summaries:\n", 1)[1]
    source_summary = source_summary.split("\n\nReturn JSON only.", 1)[0]
    assert len(source_summary) == 6000


@pytest.mark.asyncio
async def test_critic_node_falls_back_when_next_queries_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Insufficient decisions without next queries should fall back safely."""
    state = _initial_state()
    state["sub_questions"] = ["original follow-up", "second question"]
    state["iteration"] = 1
    state["total_tokens"] = 10

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        return LLMResult(
            text=(
                '{"sufficient": false, "missing_aspects": ["gap"], '
                '"next_queries": [], "reasoning": "missing evidence"}'
            ),
            total_tokens=5,
        )

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    result = await critic_node(state)

    assert result["iteration"] == 2
    assert result["total_tokens"] == 15
    assert result["critic_decision"].next_queries == ["original follow-up"]


@pytest.mark.asyncio
async def test_critic_node_emits_stage_and_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """critic_node should publish stage and critic events when emit_fn is provided."""
    state = _initial_state()
    state["iteration"] = 2
    events: list[dict] = []

    async def fake_call_llm(
        messages: list[dict],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        return LLMResult(
            text=(
                '{"sufficient": false, "missing_aspects": ["fresh data"], '
                '"next_queries": ["fresh data query"], "reasoning": "needs more"}'
            ),
            total_tokens=3,
        )

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    await critic_node(state, emit_fn=emit)

    assert events == [
        {
            "type": "stage",
            "stage": "criticizing",
            "message": "Evaluating research coverage",
        },
        {
            "type": "critic",
            "sufficient": False,
            "missing": ["fresh data"],
            "next_queries": ["fresh data query"],
            "iteration": 3,
        },
    ]


@pytest.mark.asyncio
async def test_writer_node_returns_report_citations_and_token_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """writer_node should write the final report and mark cited sources."""
    state = _initial_state()
    state["requested_language"] = "en"
    state["total_tokens"] = 50
    state["read_chunks"] = [
        ReadChunk(
            source_id=1,
            url="https://example.com/a",
            title="Example A",
            summary="Summary A",
        ),
        ReadChunk(
            source_id=2,
            url="https://example.com/b",
            title="Example B",
            summary="Summary B",
        ),
    ]
    calls: list[dict] = []

    async def fake_call_llm(messages: list[dict]) -> LLMResult:
        calls.append({"messages": messages})
        return LLMResult(text="Final answer with evidence [1].", total_tokens=19)

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    result = await writer_node(state)

    assert "Requested language: English" in calls[0]["messages"][1]["content"]
    assert result["final_report"] == "Final answer with evidence [1]."
    assert result["status"] == "done"
    assert result["total_tokens"] == 69
    assert [citation.source_id for citation in result["citations"]] == [1, 2]
    assert [citation.used_in_report for citation in result["citations"]] == [
        True,
        False,
    ]


@pytest.mark.asyncio
async def test_writer_node_emits_writing_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """writer_node should publish writing stage events when emit_fn is provided."""
    events: list[dict] = []

    async def fake_call_llm(messages: list[dict]) -> LLMResult:
        return LLMResult(text="报告 [1]", total_tokens=1)

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.nodes.call_llm", fake_call_llm)

    await writer_node(_initial_state(), emit_fn=emit)

    assert events == [
        {
            "type": "stage",
            "stage": "writing",
            "message": "Writing final report",
        },
        {"type": "writing", "message": "Writing final report"},
    ]
