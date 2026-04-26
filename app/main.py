"""FastAPI application factory and local server entry point."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.infra.db import init_db
from app.infra.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize shared resources and clean up running research tasks."""
    app.state.research_tasks = {}
    await init_db()
    yield

    tasks: dict[str, asyncio.Task] = app.state.research_tasks
    running_tasks = [task for task in tasks.values() if not task.done()]
    for task in running_tasks:
        task.cancel()
    if running_tasks:
        await asyncio.gather(*running_tasks, return_exceptions=True)


app = FastAPI(title="ez-agent", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def root_health() -> dict[str, str]:
    """Return root health status."""
    return {"status": "ok"}


def main() -> None:
    """Run the API server with uvicorn."""
    settings = get_settings()
    logger.info("Starting ez-agent API on port {}", settings.API_PORT)
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.API_PORT)


if __name__ == "__main__":
    main()
