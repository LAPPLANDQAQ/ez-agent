"""最小应用入口。"""

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(
        f"ez-agent 项目骨架已就绪,"
        f"当前运行环境为 {settings.APP_ENV},"
        f"日志级别 {settings.LOG_LEVEL}。"
    )


if __name__ == "__main__":
    main()