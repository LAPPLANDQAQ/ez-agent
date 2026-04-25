"""Research graph node implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.state import ResearchState
from app.domain.models import EmitFn, FetchTarget
from app.tools.llm import call_llm
from app.tools.fetcher import fetch_and_summarize_batch
from app.tools.search import search_multiple

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_PLANNER_PROMPT_PATH = _PROMPT_DIR / "planner.txt"


def _load_prompt(path: Path) -> str:
    """Load a prompt template from disk."""
    return path.read_text(encoding="utf-8").strip()


def _parse_sub_questions(text: str) -> list[str]:
    """Parse planner JSON and return normalized sub-questions."""
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Planner returned invalid JSON") from exc

    if isinstance(payload, dict):
        if "sub_questions" in payload:
            raw_questions = payload["sub_questions"]
        else:
            raw_questions = payload.get("questions")
    elif isinstance(payload, list):
        raw_questions = payload
    else:
        raw_questions = None

    if not isinstance(raw_questions, list):
        raise ValueError("Planner JSON must include a question list")

    questions = [str(question).strip() for question in raw_questions if question]
    questions = [question for question in questions if question]
    if not questions:
        raise ValueError("Planner returned no sub-questions")

    return questions


def _build_planner_messages(state: ResearchState) -> list[dict]:
    """Build messages for the planner LLM call."""
    prompt = _load_prompt(_PLANNER_PROMPT_PATH)
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"Research query: {state['original_query']}\n"
                f"Requested language: {state['requested_language']}\n"
                "Return JSON only."
            ),
        },
    ]


async def planner_node(
    state: ResearchState,
    *,
    emit_fn: EmitFn | None = None,
) -> dict:
    """Plan a research query into ordered sub-questions."""
    if emit_fn is not None:
        await emit_fn(
            {
                "type": "stage",
                "stage": "planning",
                "message": "Planning research sub-questions",
            }
        )

    result = await call_llm(_build_planner_messages(state), json_mode=True)
    sub_questions = _parse_sub_questions(result.text)

    if emit_fn is not None:
        await emit_fn({"type": "sub_questions", "questions": sub_questions})

    return {
        "sub_questions": sub_questions,
        "total_tokens": state["total_tokens"] + result.total_tokens,
    }


def _queries_for_search(state: ResearchState) -> list[str]:
    """Return the search queries for the current graph iteration."""
    if state["iteration"] == 0 or state["critic_decision"] is None:
        return state["sub_questions"]

    return state["critic_decision"].next_queries


async def searcher_node(
    state: ResearchState,
    *,
    emit_fn: EmitFn | None = None,
) -> dict:
    """Search for sources using initial sub-questions or critic follow-ups."""
    queries = _queries_for_search(state)

    if emit_fn is not None:
        await emit_fn(
            {
                "type": "stage",
                "stage": "searching",
                "message": "Searching for relevant sources",
            }
        )
        for query in queries:
            await emit_fn(
                {
                    "type": "searching",
                    "query": query,
                    "iteration": state["iteration"],
                }
            )

    results = await search_multiple(queries)
    return {
        "search_results": results,
        "latest_search_results": results,
    }


def _build_fetch_targets(state: ResearchState) -> list[FetchTarget]:
    """Build fetch targets from the latest search results."""
    existing_count = len(state["read_chunks"])
    return [
        FetchTarget(
            url=result.url,
            title=result.title,
            source_id=existing_count + index,
        )
        for index, result in enumerate(state["latest_search_results"], start=1)
    ]


async def reader_node(
    state: ResearchState,
    *,
    emit_fn: EmitFn | None = None,
) -> dict:
    """Fetch and summarize the latest search results."""
    targets = _build_fetch_targets(state)

    if emit_fn is not None:
        await emit_fn(
            {
                "type": "stage",
                "stage": "reading",
                "message": "Reading and summarizing sources",
            }
        )
        for target in targets:
            await emit_fn(
                {
                    "type": "reading",
                    "url": target.url,
                    "title": target.title,
                }
            )

    chunks, total_tokens = await fetch_and_summarize_batch(
        targets,
        state["original_query"],
    )
    return {
        "read_chunks": chunks,
        "latest_read_chunks": chunks,
        "total_tokens": state["total_tokens"] + total_tokens,
    }
