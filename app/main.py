"""最小应用入口。"""

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"{settings.app_name} 项目骨架已就绪，当前运行环境为 {settings.app_env}。")


if __name__ == "__main__":
    main()
