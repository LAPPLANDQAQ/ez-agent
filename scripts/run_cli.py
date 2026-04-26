"""Local command-line entry point for running the research graph."""

from __future__ import annotations

import argparse
import asyncio
from typing import Literal
from uuid import uuid4

from app.core.graph import build_graph
from app.core.state import ResearchState
from app.infra.logger import logger


async def cli_emit(event: dict) -> None:
    """Log graph events for local CLI runs."""
    logger.info("[{}] {}", event.get("type", "?"), event)


def _build_initial_state(
    query: str,
    *,
    requested_language: Literal["zh", "en"],
    max_iterations: int,
) -> ResearchState:
    """Build the complete initial state required by ResearchState."""
    return {
        "session_id": str(uuid4()),
        "original_query": query,
        "requested_language": requested_language,
        "max_iterations": max_iterations,
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


async def run_cli(
    query: str,
    *,
    requested_language: Literal["zh", "en"] = "zh",
    max_iterations: int = 3,
) -> ResearchState:
    """Run the research graph once and return the final state."""
    graph = build_graph(emit_fn=cli_emit)
    initial_state = _build_initial_state(
        query,
        requested_language=requested_language,
        max_iterations=max_iterations,
    )
    return await graph.ainvoke(initial_state)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run an ez-agent research task.")
    parser.add_argument("query", help="Research question to answer.")
    parser.add_argument(
        "--language",
        choices=["zh", "en"],
        default="zh",
        help="Final report language.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum critic/search refinement iterations.",
    )
    return parser.parse_args()


async def _main_async() -> None:
    """Run the CLI and print the final report."""
    args = _parse_args()
    result = await run_cli(
        args.query,
        requested_language=args.language,
        max_iterations=args.max_iterations,
    )
    print(result["final_report"] or "")


def main() -> None:
    """Synchronous console entry point."""
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
