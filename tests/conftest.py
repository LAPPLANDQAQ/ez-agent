"""pytest 共享 fixture。

所有测试自动获得以下隔离保障:
1. get_settings 的 lru_cache 在每个测试前后清空
2. os.environ 的修改自动回滚, 不会泄漏到后续测试
3. 文件日志自动重定向到 tmp_path, 不污染真实 logs/
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings_cache() -> Generator[None, None, None]:
    """清 get_settings 的 lru_cache, 防止跨测试污染。"""
    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except ImportError:
        pass
    yield
    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _isolate_env() -> Generator[None, None, None]:
    """保存并还原 os.environ, 防止 patch.dict 泄漏。"""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture(autouse=True)
def _redirect_log_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """把日志文件目录重定向到 tmp_path, 不污染真实 logs/。

    即使某个测试触发了 setup_file_sink(), 也会写到 tmp_path 而非项目目录。
    """
    monkeypatch.setenv("EZ_AGENT_LOG_DIR", str(tmp_path / "logs"))


@pytest.fixture
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空所有 Settings 相关的环境变量。

    用于测试"缺失必填字段应报错"的场景。
    """
    keys_to_clear = [
        "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
        "TAVILY_API_KEY", "SERPER_API_KEY",
        "QWEN_API_KEY", "ZHIPU_API_KEY",
        "DATABASE_URL", "REDIS_URL",
        "MAX_ITERATIONS", "TOKEN_BUDGET", "FETCH_TIMEOUT_SECONDS",
        "RESEARCH_TIMEOUT_SECONDS", "DEFAULT_TOP_K_PER_SEARCH",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
        "APP_ENV", "LOG_LEVEL", "API_PORT",
    ]
    for key in keys_to_clear:
        monkeypatch.delenv(key, raising=False)