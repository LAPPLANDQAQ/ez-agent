"""Search tool backed by Tavily."""

from __future__ import annotations

import asyncio
from typing import Any

from tavily import AsyncTavilyClient

from app.config import get_settings
from app.domain.errors import SearchProviderError
from app.domain.models import SearchResult


async def _search_one(
    client: AsyncTavilyClient,
    query: str,
    *,
    top_k: int,
    sub_question_index: int,
) -> list[SearchResult]:
    """Run a single Tavily search and normalize its results."""
    response = await client.search(query=query, max_results=top_k)
    raw_results = response.get("results", [])
    results: list[SearchResult] = []

    for item in raw_results:
        if not isinstance(item, dict):
            continue

        url = str(item.get("url") or "")
        if not url:
            continue

        results.append(
            SearchResult(
                url=url,
                title=str(item.get("title") or ""),
                snippet=str(item.get("content") or item.get("snippet") or ""),
                score=float(item.get("score") or 0.0),
                sub_question_index=sub_question_index,
            )
        )

    return results


async def _close_client(client: Any) -> None:
    """Close Tavily client when the concrete implementation supports it."""
    close = getattr(client, "close", None)
    if close is None:
        return

    result = close()
    if asyncio.iscoroutine(result):
        await result


async def search_multiple(
    queries: list[str],
    *,
    top_k: int = 5,
) -> list[SearchResult]:
    """Search multiple queries concurrently and deduplicate results by URL."""
    cleaned_queries = [query.strip() for query in queries]
    indexed_queries = [
        (index, query) for index, query in enumerate(cleaned_queries) if query
    ]
    if not indexed_queries:
        return []

    settings = get_settings()
    client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY.get_secret_value())

    try:
        tasks = [
            _search_one(
                client,
                query,
                top_k=top_k,
                sub_question_index=index,
            )
            for index, query in indexed_queries
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await _close_client(client)

    seen_urls: set[str] = set()
    deduplicated: list[SearchResult] = []
    failed_count = 0

    for (index, query), result in zip(indexed_queries, gathered, strict=True):
        if isinstance(result, BaseException):
            failed_count += 1
            from app.infra.logger import logger

            logger.warning(
                "Search query failed | index={} query={} error={}",
                index,
                query,
                result,
            )
            continue

        for item in result:
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            deduplicated.append(item)

    if failed_count == len(indexed_queries):
        raise SearchProviderError("All search queries failed")

    return deduplicated
