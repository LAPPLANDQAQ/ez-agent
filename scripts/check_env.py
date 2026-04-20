"""环境验证脚本。

运行方式: python scripts/check_env.py
用于验证 .env 文件配置是否正确加载。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    """验证配置加载并打印关键信息。"""
    try:
        from app.config import get_settings
    except ImportError as e:
        print(f"\n❌ 依赖未安装: {e}")
        print("\n请运行: pip install -e '.[dev]'")
        sys.exit(2)

    try:
        settings = get_settings()
    except Exception as e:
        print(f"\n❌ 配置加载失败: {e}")
        print("\n请检查:")
        print("  1. 是否已创建 .env 文件(cp .env.example .env)")
        print("  2. 是否已填入 DEEPSEEK_API_KEY 和 TAVILY_API_KEY")
        print("  3. .env 里是否有未在 app/config.py 定义的变量(extra=forbid)")
        sys.exit(1)

    print("\n✅ 配置加载成功!\n")
    print(f"  APP_ENV          = {settings.APP_ENV}")
    print(f"  LOG_LEVEL        = {settings.LOG_LEVEL}")
    print(f"  API_PORT         = {settings.API_PORT}")
    print(f"  DEEPSEEK_MODEL   = {settings.DEEPSEEK_MODEL}")
    print(f"  DEEPSEEK_BASE_URL= {settings.DEEPSEEK_BASE_URL}")
    print(f"  DATABASE_URL     = {settings.DATABASE_URL}")
    print(f"  REDIS_URL        = {settings.REDIS_URL}")
    print(f"  MAX_ITERATIONS   = {settings.MAX_ITERATIONS}")
    print(f"  TOKEN_BUDGET     = {settings.TOKEN_BUDGET}")
    print()

    warnings = []
    if settings.DEEPSEEK_API_KEY.get_secret_value().startswith("sk-your"):
        warnings.append("  ⚠️  DEEPSEEK_API_KEY 仍是占位符, 请替换为真实 Key")
    if settings.TAVILY_API_KEY.get_secret_value().startswith("tvly-your"):
        warnings.append("  ⚠️  TAVILY_API_KEY 仍是占位符, 请替换为真实 Key")

    if warnings:
        print("警告:")
        for w in warnings:
            print(w)
        print()
    else:
        print("  🎉 所有必填 Key 已配置\n")


if __name__ == "__main__":
    main()