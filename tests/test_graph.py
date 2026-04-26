"""Tests for research graph assembly and routing."""

from __future__ import annotations

import pytest

from app.core.graph import build_graph, route_after_critic
from app.core.state import ResearchState
from app.domain.models import CriticDecision, ReadChunk, SearchResult


def _initial_state() -> ResearchState:
    """Build a complete initial ResearchState for graph tests."""
    return {
        "session_id": "session-graph",
        "original_query": "How should agents validate sources?",
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
        "total_tokens": 0,
        "status": "running",
    }


def _settings_env(monkeypatch: pytest.MonkeyPatch, *, token_budget: int = 100) -> None:
    """Provide the minimum settings environment needed by graph routing."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TOKEN_BUDGET", str(token_budget))


def test_route_after_critic_respects_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routing should stop when max iterations or token budget is reached."""
    _settings_env(monkeypatch, token_budget=10)
    state = _initial_state()
    state["critic_decision"] = CriticDecision(sufficient=False, next_queries=["more"])

    assert route_after_critic(state) == "searcher"

    state["iteration"] = 3
    assert route_after_critic(state) == "writer"

    state["iteration"] = 0
    state["total_tokens"] = 10
    assert route_after_critic(state) == "writer"

    state["total_tokens"] = 0
    state["critic_decision"] = CriticDecision(sufficient=True)
    assert route_after_critic(state) == "writer"


@pytest.mark.asyncio
async def test_build_graph_runs_to_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compiled graph should execute nodes and return the final state."""
    _settings_env(monkeypatch)
    events: list[dict] = []

    async def fake_planner_node(state: ResearchState, *, emit_fn=None) -> dict:
        if emit_fn is not None:
            await emit_fn({"type": "stage", "stage": "planning"})
        return {"sub_questions": ["source validation"], "total_tokens": 1}

    async def fake_searcher_node(state: ResearchState, *, emit_fn=None) -> dict:
        result = SearchResult(
            url="https://example.com/a",
            title="Example A",
            snippet="Snippet A",
        )
        return {"search_results": [result], "latest_search_results": [result]}

    async def fake_reader_node(state: ResearchState, *, emit_fn=None) -> dict:
        chunk = ReadChunk(
            source_id=1,
            url="https://example.com/a",
            title="Example A",
            summary="Summary A",
        )
        return {
            "read_chunks": [chunk],
            "latest_read_chunks": [chunk],
            "total_tokens": state["total_tokens"] + 1,
        }

    async def fake_critic_node(state: ResearchState, *, emit_fn=None) -> dict:
        return {
            "critic_decision": CriticDecision(sufficient=True),
            "total_tokens": state["total_tokens"] + 1,
        }

    async def fake_writer_node(state: ResearchState, *, emit_fn=None) -> dict:
        return {
            "final_report": "Done [1]",
            "citations": [],
            "status": "done",
            "total_tokens": state["total_tokens"] + 1,
        }

    async def emit(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr("app.core.graph.planner_node", fake_planner_node)
    monkeypatch.setattr("app.core.graph.searcher_node", fake_searcher_node)
    monkeypatch.setattr("app.core.graph.reader_node", fake_reader_node)
    monkeypatch.setattr("app.core.graph.critic_node", fake_critic_node)
    monkeypatch.setattr("app.core.graph.writer_node", fake_writer_node)

    graph = build_graph(emit_fn=emit)
    result = await graph.ainvoke(_initial_state())

    assert result["final_report"] == "Done [1]"
    assert result["status"] == "done"
    assert result["total_tokens"] == 4
    assert result["sub_questions"] == ["source validation"]
    assert events == [{"type": "stage", "stage": "planning"}]
