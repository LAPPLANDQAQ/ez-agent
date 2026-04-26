"""结构化日志配置。

使用 loguru 替代标准 logging,提供:
- 控制台彩色输出(开发友好)— 模块 import 时即可用
- 文件日志按天轮转,JSON 格式 — 需显式调用 setup_file_sink() 启用

其他模块统一使用:
    from app.infra.logger import logger

应用启动点(main.py lifespan 或 CLI 入口)需显式启用文件 sink:
    from app.infra.logger import setup_file_sink
    setup_file_sink()

测试环境下不调用 setup_file_sink(), 或通过 EZ_AGENT_LOG_DIR 环境变量
重定向到 tmp_path, 见 tests/conftest.py 的 autouse fixture。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

from app.config import get_settings

_FILE_SINK_ID: int | None = None
_CONSOLE_CONFIGURED = False


def _setup_console_sink() -> None:
    """初始化控制台 sink。幂等:重复调用不会重复 add。"""
    global _CONSOLE_CONFIGURED
    if _CONSOLE_CONFIGURED:
        return

    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    _CONSOLE_CONFIGURED = True


def setup_file_sink(log_dir: str | Path | None = None) -> int:
    """初始化文件 sink。应在应用启动时显式调用一次。

    幂等:重复调用不会重复 add, 直接返回已有 sink id。

    Args:
        log_dir: 日志目录。优先使用参数, 其次读 EZ_AGENT_LOG_DIR 环境变量,
                 最后 fallback 到 "logs"。

    Returns:
        sink id, 可用于 logger.remove(id) 解绑。
    """
    global _FILE_SINK_ID
    if _FILE_SINK_ID is not None:
        return _FILE_SINK_ID

    raw_log_dir = log_dir
    if raw_log_dir is None:
        raw_log_dir = os.getenv("EZ_AGENT_LOG_DIR") or "logs"
    resolved_log_dir = Path(raw_log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    _FILE_SINK_ID = logger.add(
        str(resolved_log_dir / "agent_{time:YYYYMMDD}.log"),
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        serialize=True,
        encoding="utf-8",
        enqueue=True,
    )

    settings = get_settings()
    logger.info(
        "File sink initialized | dir={} env={} level={}",
        resolved_log_dir, settings.APP_ENV, settings.LOG_LEVEL,
    )
    return _FILE_SINK_ID


_setup_console_sink()

__all__ = ["logger", "setup_file_sink"]
