"""Async database models and data-access helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, asc, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from app.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Base class for ORM models."""


class ResearchSession(Base):
    """Persisted research session metadata and result fields."""

    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    requested_language: Mapped[str] = mapped_column(String(5), nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchEvent(Base):
    """Persisted SSE event with a monotonic integer cursor."""

    __tablename__ = "research_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("research_sessions.id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CitationRecord(Base):
    """Persisted citation metadata for a completed research session."""

    __tablename__ = "citation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("research_sessions.id"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    used_in_report: Mapped[bool] = mapped_column(nullable=False, default=False)


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    """Serialize a datetime as UTC ISO 8601 with Z suffix."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _session_to_dict(session: ResearchSession) -> dict:
    """Serialize a ResearchSession ORM object."""
    return {
        "session_id": session.id,
        "query": session.query,
        "status": session.status,
        "requested_language": session.requested_language,
        "max_iterations": session.max_iterations,
        "final_report": session.final_report,
        "total_tokens": session.total_tokens,
        "iteration_count": session.iteration_count,
        "duration_ms": session.duration_ms,
        "error_message": session.error_message,
        "created_at": _isoformat(session.created_at),
        "updated_at": _isoformat(session.updated_at),
    }


def _event_to_dict(event: ResearchEvent) -> dict:
    """Serialize a persisted ResearchEvent as a public event payload."""
    payload = dict(event.payload)
    payload["event_id"] = event.id
    payload.setdefault("type", event.event_type)
    if event.stage is not None:
        payload.setdefault("stage", event.stage)
    payload.setdefault("created_at", _isoformat(event.created_at))
    return payload


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the lazily initialized async session factory."""
    global _engine, _session_factory
    if _session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(settings.DATABASE_URL, future=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """Create database tables if they do not already exist."""
    factory = _get_session_factory()
    engine = factory.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_session(
    query: str,
    *,
    requested_language: Literal["zh", "en"],
    max_iterations: int,
) -> str:
    """Create a research session in created status and return its ID."""
    session_id = str(uuid4())
    now = _now()
    record = ResearchSession(
        id=session_id,
        query=query,
        status="created",
        requested_language=requested_language,
        max_iterations=max_iterations,
        total_tokens=0,
        iteration_count=0,
        created_at=now,
        updated_at=now,
    )

    async with _get_session_factory()() as db:
        db.add(record)
        await db.commit()

    return session_id


async def claim_session_start(session_id: str) -> bool:
    """Atomically mark a created session as running."""
    async with _get_session_factory()() as db:
        result = await db.execute(
            update(ResearchSession)
            .where(
                ResearchSession.id == session_id,
                ResearchSession.status == "created",
            )
            .values(status="running", updated_at=_now())
        )
        await db.commit()
        return getattr(result, "rowcount", 0) == 1


async def update_session(session_id: str, **kwargs: Any) -> None:
    """Update mutable fields for one research session."""
    kwargs["updated_at"] = _now()
    async with _get_session_factory()() as db:
        await db.execute(
            update(ResearchSession)
            .where(ResearchSession.id == session_id)
            .values(**kwargs)
        )
        await db.commit()


async def get_session(session_id: str) -> dict | None:
    """Return one session by ID, or None when absent."""
    async with _get_session_factory()() as db:
        result = await db.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
    if session is None:
        return None
    return _session_to_dict(session)


async def list_citations(session_id: str) -> list[dict]:
    """Return persisted citation records for one session."""
    async with _get_session_factory()() as db:
        result = await db.execute(
            select(CitationRecord)
            .where(CitationRecord.session_id == session_id)
            .order_by(asc(CitationRecord.source_id))
        )
        citations = result.scalars().all()
    return [
        {
            "source_id": citation.source_id,
            "url": citation.url,
            "title": citation.title,
            "snippet": citation.snippet,
            "used_in_report": citation.used_in_report,
        }
        for citation in citations
    ]


async def list_sessions(limit: int = 20) -> list[dict]:
    """Return recent research sessions."""
    async with _get_session_factory()() as db:
        result = await db.execute(
            select(ResearchSession)
            .order_by(desc(ResearchSession.created_at))
            .limit(limit)
        )
        sessions = result.scalars().all()
    return [_session_to_dict(session) for session in sessions]


async def save_events(session_id: str, events: list[dict]) -> None:
    """Persist a batch of historical events."""
    for event in events:
        await save_single_event(session_id, event)


async def save_single_event(session_id: str, event: dict) -> dict:
    """Persist one event and return it with an event_id cursor."""
    now = _now()
    event_type = str(event.get("type", event.get("event_type", "message")))
    stage = event.get("stage")
    record = ResearchEvent(
        session_id=session_id,
        event_type=event_type,
        stage=str(stage) if stage is not None else None,
        payload=dict(event),
        created_at=now,
    )

    async with _get_session_factory()() as db:
        db.add(record)
        await db.commit()
        await db.refresh(record)

    return _event_to_dict(record)


async def list_events(
    session_id: str,
    *,
    after_event_id: int = 0,
) -> list[dict]:
    """Return events with event_id greater than after_event_id."""
    async with _get_session_factory()() as db:
        result = await db.execute(
            select(ResearchEvent)
            .where(
                ResearchEvent.session_id == session_id,
                ResearchEvent.id > after_event_id,
            )
            .order_by(asc(ResearchEvent.id))
        )
        events = result.scalars().all()
    return [_event_to_dict(event) for event in events]


async def save_citations(session_id: str, citations: list[dict]) -> None:
    """Persist citation records for one session."""
    records = [
        CitationRecord(
            session_id=session_id,
            source_id=int(citation["source_id"]),
            url=str(citation["url"]),
            title=str(citation["title"]),
            snippet=str(citation.get("snippet", "")),
            used_in_report=bool(citation.get("used_in_report", False)),
        )
        for citation in citations
    ]
    async with _get_session_factory()() as db:
        db.add_all(records)
        await db.commit()
