"""Commit #1 测试: 配置加载 + 日志系统。"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestSettings:
    """测试 app.config.Settings 配置加载。"""

    def test_load_with_required_env_vars(self) -> None:
        """必填字段存在时应正常加载。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test-key",
            "TAVILY_API_KEY": "tvly-test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import Settings

            settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert settings.DEEPSEEK_API_KEY.get_secret_value() == "sk-test-key"
        assert settings.TAVILY_API_KEY.get_secret_value() == "tvly-test-key"
        assert settings.DEEPSEEK_MODEL == "deepseek-chat"
        assert settings.APP_ENV == "development"

    def test_missing_required_field_raises_error(
        self, clean_settings_env: None
    ) -> None:
        """缺少必填字段时应抛出 ValidationError。"""
        from pydantic import ValidationError

        from app.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]

        error_text = str(exc_info.value)
        assert "DEEPSEEK_API_KEY" in error_text or "TAVILY_API_KEY" in error_text

    def test_default_values(self) -> None:
        """有默认值的字段应使用默认值。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import Settings

            settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert settings.MAX_ITERATIONS == 3
        assert settings.TOKEN_BUDGET == 100_000
        assert settings.FETCH_TIMEOUT_SECONDS == 10
        assert settings.RESEARCH_TIMEOUT_SECONDS == 90
        assert settings.DEFAULT_TOP_K_PER_SEARCH == 5
        assert settings.LOG_LEVEL == "INFO"
        assert settings.API_PORT == 8000

    def test_env_override(self) -> None:
        """环境变量应能覆盖默认值。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
            "MAX_ITERATIONS": "5",
            "TOKEN_BUDGET": "200000",
            "LOG_LEVEL": "DEBUG",
            "APP_ENV": "production",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import Settings

            settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert settings.MAX_ITERATIONS == 5
        assert settings.TOKEN_BUDGET == 200_000
        assert settings.LOG_LEVEL == "DEBUG"
        assert settings.APP_ENV == "production"

    def test_invalid_log_level_rejected(self) -> None:
        """非法 LOG_LEVEL 应在加载时报错。"""
        from pydantic import ValidationError

        from app.config import Settings

        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
            "LOG_LEVEL": "VERBOSE",
        }
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)  # type: ignore[call-arg]

    def test_extra_field_rejected(self) -> None:
        """拼写错误的字段应被 extra='forbid' 拦截。"""
        from pydantic import ValidationError

        from app.config import Settings

        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings(
                    _env_file=None,  # type: ignore[call-arg]
                    TYPO_KEY="oops",  # type: ignore[call-arg]
                )

    def test_secret_str_not_leaked_in_repr(self) -> None:
        """SecretStr 应在 repr 中遮蔽。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-super-secret",
            "TAVILY_API_KEY": "tvly-also-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import Settings

            settings = Settings(_env_file=None)  # type: ignore[call-arg]

        settings_repr = repr(settings)
        assert "sk-super-secret" not in settings_repr
        assert "tvly-also-secret" not in settings_repr
        assert settings.DEEPSEEK_API_KEY.get_secret_value() == "sk-super-secret"

    def test_database_url_default_is_sqlite(self) -> None:
        """开发环境默认使用 SQLite。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import Settings

            settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert "sqlite" in settings.DATABASE_URL


class TestLogger:
    """测试 app.infra.logger 日志系统。"""

    def test_logger_import_only_console(self) -> None:
        """模块 import 应只初始化控制台 sink, 不创建文件。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.infra import logger as logger_module

        assert logger_module.logger is not None
        assert logger_module._FILE_SINK_ID is None

    def test_logger_can_log(self) -> None:
        """logger 应能正常输出到自定义 sink。"""
        import io

        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.infra.logger import logger

            buffer = io.StringIO()
            sink_id = logger.add(buffer, format="{message}")
            logger.info("test message from unit test")
            logger.remove(sink_id)

        output = buffer.getvalue()
        assert "test message" in output

    def test_setup_file_sink_creates_log_dir(self, tmp_path) -> None:
        """setup_file_sink 应创建日志目录并返回 sink id。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        log_dir = tmp_path / "custom_logs"
        with patch.dict(os.environ, env, clear=False):
            from app.infra.logger import logger, setup_file_sink

            sink_id = setup_file_sink(log_dir=log_dir)

            assert log_dir.exists()
            assert sink_id is not None

            logger.remove(sink_id)
            import app.infra.logger as logger_module
            logger_module._FILE_SINK_ID = None

    def test_setup_file_sink_is_idempotent(self, tmp_path) -> None:
        """setup_file_sink 重复调用应返回同一个 sink id。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "TAVILY_API_KEY": "tvly-test",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.infra.logger import logger, setup_file_sink

            id1 = setup_file_sink(log_dir=tmp_path / "logs1")
            id2 = setup_file_sink(log_dir=tmp_path / "logs2")

            assert id1 == id2

            logger.remove(id1)
            import app.infra.logger as logger_module
            logger_module._FILE_SINK_ID = None