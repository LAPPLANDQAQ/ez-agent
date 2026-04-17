"""SSE 事件格式辅助函数。"""


def format_sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"
