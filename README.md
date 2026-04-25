# ez-agent

`ez-agent` 是一个面向自动化深度研究场景的 Python Agent 项目。当前仓库按分阶段
commit 演进：配置与日志基础设施已经完成，工具层已经接入 LLM、Tavily 搜索、网页抓取
和 Redis 缓存；核心状态模型与 planner 节点已经开始落地。完整状态图、API、SSE、
前端和部署会在后续 commit 中继续实现。

## 项目已实现和为实现功能

已完成：

- 配置加载：`app/config.py` 使用 `pydantic-settings`，必填 `DEEPSEEK_API_KEY` 和
  `TAVILY_API_KEY`，敏感字段使用 `SecretStr`。
- 日志系统：`app/infra/logger.py` 使用 `loguru`，默认控制台输出，文件 sink 需要显式
  调用 `setup_file_sink()`。
- LLM 工具：`app/tools/llm.py` 提供异步 `call_llm()`，使用 `ChatOpenAI` 调用
  DeepSeek 兼容接口，支持 JSON mode、每模型 3 次重试、fallback 模型和 token 统计回退。
- 搜索工具：`app/tools/search.py` 提供异步 `search_multiple()`，使用
  `AsyncTavilyClient` 并发搜索，支持单 query 失败不中断、按 URL 去重和
  `sub_question_index` 标记。
- 缓存工具：`app/infra/cache.py` 提供异步 `cache_get()` 和 `cache_setex()`，
  Redis 客户端懒初始化，Redis 不可用时降级到单进程内存缓存。
- 抓取工具：`app/tools/fetcher.py` 提供异步 `fetch_and_summarize_batch()`，
  使用 `httpx` 抓取网页、`trafilatura` 提取正文、`call_llm()` 生成摘要，并缓存
  `ReadChunk`。
- 领域模型：`app/domain/models.py` 已包含 `LLMResult`、`SearchResult`、
  `FetchTarget`、`ReadChunk`、`CriticDecision`、`Citation` 和 `EmitFn`。
- 研究状态：`app/core/state.py` 定义 `ResearchState`，包括请求级语言、最大迭代次数、
  搜索结果、阅读片段、critic 决策、引用、token 统计和运行状态。
- Planner 节点：`app/core/nodes.py` 提供异步 `planner_node()`，读取
  `app/core/prompts/planner.txt`，通过 `call_llm(json_mode=True)` 生成子问题，并累加
  `total_tokens`。

尚未完成：

- LangGraph 完整执行图。
- Searcher、Reader、Critic、Writer 节点。
- FastAPI 路由、数据库层、SSE 事件流和 runner。
- Streamlit 前端、Docker 部署和项目收尾文档。

## 目录结构

```text
ez-agent/
+-- app/
|   +-- api/
|   +-- core/
|   |   +-- prompts/
|   +-- domain/
|   +-- infra/
|   +-- tools/
|   +-- config.py
|   +-- main.py
+-- frontend/
+-- scripts/
+-- tests/
+-- .env.example
+-- Makefile
+-- pyproject.toml
+-- README.md
```

## 环境要求

- Python 3.12+
- DeepSeek API Key
- Tavily API Key
- Redis，生产或联调时使用；本地单进程开发可依赖内存降级

## 安装依赖

建议先创建虚拟环境，再以可编辑模式安装开发依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

如果默认 PyPI 下载较慢，可以临时使用清华镜像：

```powershell
pip install -e .[dev] -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 配置环境变量

复制示例环境文件：

```powershell
Copy-Item .env.example .env
```

至少填写：

```env
DEEPSEEK_API_KEY=your-deepseek-api-key
TAVILY_API_KEY=your-tavily-api-key
```

常用可选项：

```env
REDIS_URL=redis://localhost:6379/0
FETCH_TIMEOUT_SECONDS=10
```

可以运行配置检查脚本：

```powershell
python scripts/check_env.py
```

注意：`app/config.py` 设置了 `extra="forbid"`，`.env` 中不要放未定义的应用配置项。

## 本地运行

当前 CLI 仍是最小入口，只验证配置加载和基础启动：

```powershell
python -m app.main
```

或：

```powershell
python scripts/run_cli.py
```

完整研究流程会在后续 searcher、reader、critic、writer、graph、runner 和 API commit
中实现。

## 工具层接口

LLM 调用：

```python
from app.tools.llm import call_llm

result = await call_llm(
    [{"role": "user", "content": "用一句话解释 LangGraph"}],
    json_mode=False,
    temperature=0.3,
    max_tokens=4096,
)
```

搜索调用：

```python
from app.tools.search import search_multiple

results = await search_multiple(
    ["LangGraph multi-agent architecture", "Deep research agent design"],
    top_k=5,
)
```

抓取和摘要：

```python
from app.domain.models import FetchTarget
from app.tools.fetcher import fetch_and_summarize_batch

chunks, total_tokens = await fetch_and_summarize_batch(
    [
        FetchTarget(
            url="https://example.com/article",
            title="Example Article",
            source_id=1,
        )
    ],
    query="Deep research agent design",
)
```

缓存接口：

```python
from app.infra.cache import cache_get, cache_setex

await cache_setex("example:key", 60, "value")
value = await cache_get("example:key")
```

Planner 节点：

```python
from app.core.nodes import planner_node

result = await planner_node(initial_state)
sub_questions = result["sub_questions"]
```

## 测试

运行完整测试：

```powershell
pytest
```

当前阶段重点测试：

```powershell
pytest tests/test_config.py tests/test_tools.py -v
```

如果 Windows 环境下 pytest 临时目录权限异常，可以指定仓库内临时目录：

```powershell
New-Item -ItemType Directory -Force -Path tmp_pytest
pytest -q -p no:cacheprovider --basetemp="C:\code\ez-agent\tmp_pytest\all"
```
