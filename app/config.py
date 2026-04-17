"""应用配置辅助函数。"""

from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    app_name: str = "ez-agent"
    app_env: str = "development"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "ez-agent"),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
