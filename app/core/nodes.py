"""Research graph node implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.state import ResearchState
from app.domain.models import EmitFn
from app.tools.llm import call_llm

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
