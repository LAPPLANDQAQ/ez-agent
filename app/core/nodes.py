"""Research graph node implementations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.state import ResearchState
from app.domain.models import Citation, CriticDecision, EmitFn, FetchTarget
from app.infra.logger import logger
from app.tools.llm import call_llm
from app.tools.fetcher import fetch_and_summarize_batch
from app.tools.search import search_multiple

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_PLANNER_PROMPT_PATH = _PROMPT_DIR / "planner.txt"
_CRITIC_PROMPT_PATH = _PROMPT_DIR / "critic.txt"
_WRITER_PROMPT_PATH = _PROMPT_DIR / "writer.txt"
_CHUNKS_SUMMARY_LIMIT = 6000
_CITATION_PATTERN = re.compile(r"\[(?:source\s*)?(\d+)\]", re.IGNORECASE)


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


def _build_chunks_summary(state: ResearchState) -> str:
    """Build a bounded source summary for the critic prompt."""
    parts = [
        (
            f"[{chunk.source_id}] {chunk.title}\n"
            f"URL: {chunk.url}\n"
            f"Summary: {chunk.summary}"
        )
        for chunk in state["read_chunks"]
    ]
    return "\n\n".join(parts)[:_CHUNKS_SUMMARY_LIMIT]


def _parse_critic_decision(text: str) -> CriticDecision:
    """Parse critic JSON and return a validated decision."""
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Critic returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Critic JSON must be an object")

    return CriticDecision.model_validate(payload)


def _build_critic_messages(state: ResearchState) -> list[dict]:
    """Build messages for the critic LLM call."""
    prompt = _load_prompt(_CRITIC_PROMPT_PATH)
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"Research query: {state['original_query']}\n"
                f"Sub-questions: {json.dumps(state['sub_questions'], ensure_ascii=False)}\n"
                f"Iteration: {state['iteration']}\n"
                f"Source summaries:\n{_build_chunks_summary(state)}\n\n"
                "Return JSON only."
            ),
        },
    ]


def _normalize_critic_decision(
    decision: CriticDecision,
    state: ResearchState,
) -> CriticDecision:
    """Apply required fallback behavior to a critic decision."""
    if not decision.sufficient and not decision.next_queries:
        decision.next_queries = state["sub_questions"][:1]
        logger.warning(
            "Critic returned empty next_queries; fallback to first sub-question"
        )
    return decision


async def critic_node(
    state: ResearchState,
    *,
    emit_fn: EmitFn | None = None,
) -> dict:
    """Evaluate whether the gathered evidence is sufficient for writing."""
    if emit_fn is not None:
        await emit_fn(
            {
                "type": "stage",
                "stage": "criticizing",
                "message": "Evaluating research coverage",
            }
        )

    result = await call_llm(_build_critic_messages(state), json_mode=True)
    decision = _normalize_critic_decision(_parse_critic_decision(result.text), state)
    next_iteration = state["iteration"] + 1 if not decision.sufficient else state["iteration"]

    if emit_fn is not None:
        await emit_fn(
            {
                "type": "critic",
                "sufficient": decision.sufficient,
                "missing": decision.missing_aspects,
                "next_queries": decision.next_queries,
                "iteration": next_iteration,
            }
        )

    update = {
        "critic_decision": decision,
        "total_tokens": state["total_tokens"] + result.total_tokens,
    }
    if not decision.sufficient:
        update["iteration"] = next_iteration

    return update


def _build_writer_context(state: ResearchState) -> str:
    """Build source context for the writer prompt."""
    parts = [
        (
            f"[{chunk.source_id}] {chunk.title}\n"
            f"URL: {chunk.url}\n"
            f"Summary: {chunk.summary}"
        )
        for chunk in state["read_chunks"]
    ]
    return "\n\n".join(parts)


def _citation_ids_used(report: str) -> set[int]:
    """Extract source IDs cited by bracketed report references."""
    return {int(match.group(1)) for match in _CITATION_PATTERN.finditer(report)}


def _build_citations(state: ResearchState, report: str) -> list[Citation]:
    """Build citation records and mark sources referenced by the final report."""
    used_source_ids = _citation_ids_used(report)
    return [
        Citation(
            source_id=chunk.source_id,
            url=chunk.url,
            title=chunk.title,
            snippet=chunk.summary[:300],
            used_in_report=chunk.source_id in used_source_ids,
        )
        for chunk in state["read_chunks"]
    ]


def _build_writer_messages(state: ResearchState) -> list[dict]:
    """Build messages for the final report writer LLM call."""
    prompt = _load_prompt(_WRITER_PROMPT_PATH)
    language_name = "Chinese" if state["requested_language"] == "zh" else "English"
    critic_summary = ""
    if state["critic_decision"] is not None:
        critic_summary = state["critic_decision"].model_dump_json()

    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"Research query: {state['original_query']}\n"
                f"Requested language: {language_name}\n"
                f"Critic decision: {critic_summary}\n"
                f"Source context:\n{_build_writer_context(state)}\n\n"
                "Write the final report now. Cite sources with bracketed source "
                "IDs like [1]."
            ),
        },
    ]


async def writer_node(
    state: ResearchState,
    *,
    emit_fn: EmitFn | None = None,
) -> dict:
    """Write the final report and derive citation usage."""
    if emit_fn is not None:
        await emit_fn(
            {
                "type": "stage",
                "stage": "writing",
                "message": "Writing final report",
            }
        )
        await emit_fn({"type": "writing", "message": "Writing final report"})

    result = await call_llm(_build_writer_messages(state))
    report = result.text.strip()

    return {
        "final_report": report,
        "citations": _build_citations(state, report),
        "status": "done",
        "total_tokens": state["total_tokens"] + result.total_tokens,
    }
