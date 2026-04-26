"""Streamlit UI for ez-agent research sessions."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx
import streamlit as st

DEFAULT_API_BASE_URL = "http://localhost:8000"


def _api_base_url() -> str:
    """Return the configured API base URL."""
    return os.getenv("EZ_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def _client() -> httpx.Client:
    """Build a synchronous HTTP client for Streamlit callbacks."""
    return httpx.Client(base_url=_api_base_url(), timeout=None)


def _create_session(
    query: str,
    *,
    language: str,
    max_iterations: int,
) -> dict[str, Any]:
    """Create a research session through the API."""
    with _client() as client:
        response = client.post(
            "/api/v1/research",
            json={
                "query": query,
                "language": language,
                "max_iterations": max_iterations,
            },
        )
        response.raise_for_status()
        return response.json()


def _list_sessions() -> list[dict[str, Any]]:
    """Load recent sessions for the sidebar."""
    try:
        with _client() as client:
            response = client.get("/api/v1/research", params={"limit": 20})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        return []


def _parse_sse_line(buffer: dict[str, str], line: str) -> dict[str, Any] | None:
    """Parse one SSE line into a complete event when possible."""
    if not line:
        if "data" not in buffer:
            buffer.clear()
            return None
        data = json.loads(buffer["data"])
        event = {"event": buffer.get("event", "message"), **data}
        buffer.clear()
        return event

    field, _, value = line.partition(":")
    if field in {"event", "id", "data"}:
        buffer[field] = value.lstrip()
    return None


def _stream_events(stream_url: str) -> Iterator[dict[str, Any]]:
    """Yield parsed SSE events from a research stream."""
    buffer: dict[str, str] = {}
    with _client() as client:
        with client.stream("GET", stream_url) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                event = _parse_sse_line(buffer, line)
                if event is not None:
                    yield event
                    if event.get("type") in {"done", "error"}:
                        return


def _render_history() -> None:
    """Render recent session history in the sidebar."""
    st.sidebar.header("History")
    sessions = _list_sessions()
    if not sessions:
        st.sidebar.caption("No sessions yet")
        return

    for session in sessions:
        label = f"{session['status']} · {session['query'][:48]}"
        with st.sidebar.expander(label):
            st.caption(session["session_id"])
            st.write(f"Language: {session['requested_language']}")
            st.write(f"Iterations: {session['iteration_count']}")
            st.write(f"Tokens: {session['total_tokens']}")


def _render_event(event: dict[str, Any]) -> None:
    """Render one live event."""
    event_type = event.get("type", event.get("event", "message"))
    if event_type == "stage":
        st.status(event.get("message", event.get("stage", "stage")), expanded=False)
    elif event_type == "sub_questions":
        st.write("Sub-questions")
        for question in event.get("questions", []):
            st.write(f"- {question}")
    elif event_type == "critic":
        st.write(
            {
                "sufficient": event.get("sufficient"),
                "missing": event.get("missing", []),
                "next_queries": event.get("next_queries", []),
            }
        )
    elif event_type == "error":
        st.error(f"{event.get('code')}: {event.get('message')}")
    elif event_type == "done":
        return
    else:
        st.write(event)


def main() -> None:
    """Render the Streamlit application."""
    st.set_page_config(page_title="ez-agent", layout="wide")
    st.title("ez-agent")
    st.caption("Automated research workspace")
    _render_history()

    with st.form("research-form"):
        query = st.text_area("Research question", height=120)
        language = st.segmented_control("Language", ["zh", "en"], default="zh")
        max_iterations = st.slider("Max iterations", min_value=1, max_value=5, value=3)
        submitted = st.form_submit_button("Run research", type="primary")

    if not submitted:
        return

    if not query.strip():
        st.warning("Enter a research question.")
        return

    session = _create_session(
        query.strip(),
        language=language,
        max_iterations=max_iterations,
    )
    st.session_state["active_session_id"] = session["session_id"]
    st.write(f"Session: `{session['session_id']}`")

    events_container = st.container()
    report_container = st.container()
    with events_container:
        for event in _stream_events(session["stream_url"]):
            if event.get("type") == "done":
                with report_container:
                    st.markdown(event.get("report") or "")
                    citations = event.get("citations", [])
                    if citations:
                        st.subheader("Citations")
                        st.dataframe(citations, use_container_width=True)
                break
            _render_event(event)


if __name__ == "__main__":
    main()
