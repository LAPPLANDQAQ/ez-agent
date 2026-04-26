"""Web fetcher that extracts page text and summarizes it."""

from __future__ import annotations

import asyncio
import hashlib

import httpx
import trafilatura

from app.config import get_settings
from app.domain.errors import FetchProviderError
from app.domain.models import FetchTarget, ReadChunk
from app.infra.cache import cache_get, cache_setex
from app.tools.llm import call_llm

_CACHE_TTL_SECONDS = 60 * 60 * 24
_MAX_TEXT_CHARS = 12000


def _cache_key(target: FetchTarget, query: str) -> str:
    """Build a stable cache key for a target and query pair."""
    digest = hashlib.sha256(f"{target.url}\n{query}".encode("utf-8")).hexdigest()
    return f"fetch_summary:{digest}"


def _chunk_from_cache(value: str) -> ReadChunk | None:
    """Parse a cached read chunk."""
    try:
        return ReadChunk.model_validate_json(value)
    except ValueError:
        return None


def _serialize_chunk(chunk: ReadChunk) -> str:
    """Serialize a read chunk for cache storage."""
    return chunk.model_dump_json()


def _extract_text(html: str) -> str:
    """Extract readable page text from raw HTML."""
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if extracted:
        return extracted.strip()
    return ""


def _build_summary_prompt(target: FetchTarget, query: str, text: str) -> list[dict]:
    """Build messages for source summarization."""
    clipped_text = text[:_MAX_TEXT_CHARS]
    return [
        {
            "role": "system",
            "content": (
                "You summarize fetched web pages for a research agent. "
                "Return a concise factual summary focused on the user's query."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Query: {query}\n"
                f"Source title: {target.title}\n"
                f"Source URL: {target.url}\n\n"
                f"Page text:\n{clipped_text}"
            ),
        },
    ]


async def _fetch_target(
    client: httpx.AsyncClient,
    target: FetchTarget,
    *,
    query: str,
) -> tuple[ReadChunk, int]:
    """Fetch, extract, summarize, and cache a single target."""
    key = _cache_key(target, query)
    cached = await cache_get(key)
    if cached is not None:
        chunk = _chunk_from_cache(cached)
        if chunk is not None:
            return chunk, 0

    response = await client.get(target.url)
    response.raise_for_status()

    text = _extract_text(response.text)
    if not text:
        raise ValueError(f"No readable content extracted from {target.url}")

    result = await call_llm(_build_summary_prompt(target, query, text), max_tokens=1024)
    chunk = ReadChunk(
        source_id=target.source_id,
        url=target.url,
        title=target.title,
        summary=result.text,
        raw_length=len(text),
    )
    await cache_setex(key, _CACHE_TTL_SECONDS, _serialize_chunk(chunk))
    return chunk, result.total_tokens


async def fetch_and_summarize_batch(
    targets: list[FetchTarget],
    query: str,
) -> tuple[list[ReadChunk], int]:
    """Fetch and summarize a batch of targets, skipping failed URLs."""
    if not targets:
        return [], 0

    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        gathered = await asyncio.gather(
            *[_fetch_target(client, target, query=query) for target in targets],
            return_exceptions=True,
        )

    chunks: list[ReadChunk] = []
    total_tokens = 0
    failed_count = 0

    for target, result in zip(targets, gathered, strict=True):
        if isinstance(result, BaseException):
            failed_count += 1
            from app.infra.logger import logger

            logger.warning(
                "Fetch target failed | source_id={} url={} error={}",
                target.source_id,
                target.url,
                result,
            )
            continue

        chunk, tokens = result
        chunks.append(chunk)
        total_tokens += tokens

    if failed_count == len(targets):
        raise FetchProviderError("All fetch targets failed")

    return chunks, total_tokens
