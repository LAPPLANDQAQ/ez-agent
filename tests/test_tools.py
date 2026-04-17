from app.tools.fetcher import fetch
from app.tools.llm import generate
from app.tools.search import search


def test_generate_returns_placeholder() -> None:
    assert generate("你好").startswith("[大模型占位响应]")


def test_search_returns_list() -> None:
    assert search("智能体") == ["搜索结果：智能体"]


def test_fetch_returns_status() -> None:
    assert fetch("https://example.com")["status"] == "尚未实现"
