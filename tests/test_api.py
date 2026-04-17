from app.api.routes import list_routes
from app.api.sse import format_sse


def test_list_routes_contains_health() -> None:
    assert "/health" in list_routes()


def test_format_sse_layout() -> None:
    assert format_sse("message", "你好") == "event: message\ndata: 你好\n\n"
