"""Commit #5 tests for research state and planner node."""

from __future__ import annotations

import pytest

from app.core.nodes import planner_node
from app.core.state import ResearchState
from app.domain.models import LLMResult


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
