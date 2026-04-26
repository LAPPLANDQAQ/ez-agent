"""Small local evaluation runner for ez-agent research tasks."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from app.core.runner import run_research_cli


def _parse_args() -> argparse.Namespace:
    """Parse evaluation command-line arguments."""
    parser = argparse.ArgumentParser(description="Run one ez-agent eval query.")
    parser.add_argument("query", help="Research question to evaluate.")
    parser.add_argument("--language", choices=["zh", "en"], default="zh")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


async def run_eval(
    query: str,
    *,
    requested_language: Literal["zh", "en"] = "zh",
    max_iterations: int = 3,
) -> dict:
    """Run one eval query and return a compact result payload."""
    state = await run_research_cli(
        query=query,
        requested_language=requested_language,
        max_iterations=max_iterations,
    )
    return {
        "query": query,
        "status": state["status"],
        "total_tokens": state["total_tokens"],
        "iterations": state["iteration"],
        "final_report": state["final_report"],
        "citations": [citation.model_dump() for citation in state["citations"]],
    }


async def _main_async() -> None:
    """Run the eval CLI."""
    args = _parse_args()
    language: Literal["zh", "en"] = args.language
    result = await run_eval(
        args.query,
        requested_language=language,
        max_iterations=args.max_iterations,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


def main() -> None:
    """Synchronous script entry point."""
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
