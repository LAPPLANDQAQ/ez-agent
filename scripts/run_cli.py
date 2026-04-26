"""Local command-line entry point for running the research graph."""

from __future__ import annotations

import argparse
import asyncio
from typing import Literal

from app.core.runner import run_research_cli
from app.infra.logger import logger


async def cli_emit(event: dict) -> None:
    """Log graph events for local CLI runs."""
    logger.info("[{}] {}", event.get("type", "?"), event)


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
    language: Literal["zh", "en"] = args.language
    result = await run_research_cli(
        query=args.query,
        requested_language=language,
        max_iterations=args.max_iterations,
        emit_fn=cli_emit,
    )
    print(result["final_report"] or "")


def main() -> None:
    """Synchronous console entry point."""
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
