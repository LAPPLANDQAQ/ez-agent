"""LangGraph assembly for the research workflow."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.core.nodes import (
    critic_node,
    planner_node,
    reader_node,
    searcher_node,
    writer_node,
)
from app.core.state import ResearchState
from app.domain.models import EmitFn


def route_after_critic(state: ResearchState) -> str:
    """Route to writer when research is sufficient or bounded by limits."""
    settings = get_settings()
    if state["iteration"] >= state["max_iterations"]:
        return "writer"
    if state["total_tokens"] >= settings.TOKEN_BUDGET:
        return "writer"
    if state["critic_decision"] and state["critic_decision"].sufficient:
        return "writer"
    return "searcher"


def build_graph(*, emit_fn: EmitFn | None = None):
    """Build and compile the research graph with an optional event emitter."""

    async def plan(state: ResearchState) -> dict:
        return await planner_node(state, emit_fn=emit_fn)

    async def search(state: ResearchState) -> dict:
        return await searcher_node(state, emit_fn=emit_fn)

    async def read(state: ResearchState) -> dict:
        return await reader_node(state, emit_fn=emit_fn)

    async def critique(state: ResearchState) -> dict:
        return await critic_node(state, emit_fn=emit_fn)

    async def write(state: ResearchState) -> dict:
        return await writer_node(state, emit_fn=emit_fn)

    graph = StateGraph(ResearchState)
    graph.add_node("planner", plan)
    graph.add_node("searcher", search)
    graph.add_node("reader", read)
    graph.add_node("critic", critique)
    graph.add_node("writer", write)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "searcher")
    graph.add_edge("searcher", "reader")
    graph.add_edge("reader", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"searcher": "searcher", "writer": "writer"},
    )
    graph.add_edge("writer", END)

    return graph.compile()
