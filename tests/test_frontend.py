"""Tests for frontend-only helpers."""

from __future__ import annotations

from frontend.api_client import EzAgentClient


def test_parse_sse_tolerates_malformed_event_id() -> None:
    """Malformed SSE id fields should not break the client stream parser."""
    events = list(
        EzAgentClient._parse_sse(
            iter(
                [
                    "event: stage",
                    "id: not-an-int",
                    'data: {"stage": "planning"}',
                    "",
                ]
            )
        )
    )

    assert events == [
        {
            "type": "stage",
            "data": {"stage": "planning"},
            "event_id": None,
        }
    ]
