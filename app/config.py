"""应用配置中心。

使用 pydantic-settings 从 .env 文件和环境变量加载配置,
提供类型安全的配置对象,缺少必填字段时抛出明确错误。

敏感字段(API Key)使用 SecretStr 保护,避免在日志和异常中泄漏。
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置,按优先级加载:环境变量 > .env 文件 > 默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=True,
    )

    # ========= LLM(必填) =========
    DEEPSEEK_API_KEY: SecretStr
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ========= 备用 LLM(可选) =========
    QWEN_API_KEY: SecretStr = SecretStr("")
    ZHIPU_API_KEY: SecretStr = SecretStr("")

    # ========= 搜索(必填) =========
    TAVILY_API_KEY: SecretStr
    SERPER_API_KEY: SecretStr = SecretStr("")

    # ========= 数据库 =========
    DATABASE_URL: str = "sqlite+aiosqlite:///./research.db"

    # ========= Redis =========
    REDIS_URL: str = "redis://localhost:6379/0"

    # ========= Agent 参数 =========
    MAX_ITERATIONS: int = 3
    TOKEN_BUDGET: int = 100_000
    FETCH_TIMEOUT_SECONDS: int = 10
    RESEARCH_TIMEOUT_SECONDS: int = 90
    DEFAULT_TOP_K_PER_SEARCH: int = 5

    # ========= 可观测性(可选) =========
    LANGFUSE_PUBLIC_KEY: SecretStr = SecretStr("")
    LANGFUSE_SECRET_KEY: SecretStr = SecretStr("")
    LANGFUSE_HOST: str = ""

    # ========= 应用 =========
    APP_ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    API_PORT: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局配置单例。使用 lru_cache 确保只加载一次。

    测试环境需要在 fixture 中调用 get_settings.cache_clear() 防止污染。
    """
    return Settings()  # type: ignore[call-arg]