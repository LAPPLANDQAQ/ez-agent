# ez-agent

`ez-agent` 是一个面向自动化深度研究场景的 Python Agent 项目。当前仓库按分阶段
commit 演进：配置与日志基础设施已经完成，工具层已经接入 LLM、Tavily 搜索、网页抓取
和 Redis 缓存；核心状态模型、planner、searcher、reader、critic、writer 节点、
LangGraph 执行图、live 事件总线、SSE 事件生成器、FastAPI 路由、数据库层、runner
和 Streamlit 前端已经落地。部署会在后续 commit 中继续实现。

## 项目已实现和未实现功能

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
- Searcher 节点：`app/core/nodes.py` 提供异步 `searcher_node()`，首轮使用
  `sub_questions` 搜索，后续轮次使用 `critic_decision.next_queries` 搜索，并维护
  `search_results` 与 `latest_search_results`。
- Reader 节点：`app/core/nodes.py` 提供异步 `reader_node()`，只消费
  `latest_search_results`，为结果分配连续 `source_id`，调用抓取摘要工具生成
  `ReadChunk`，并累加 `total_tokens`。
- Critic 节点：`app/core/nodes.py` 提供异步 `critic_node()`，读取
  `app/core/prompts/critic.txt`，通过 `call_llm(json_mode=True)` 判断证据是否充分，
  在 `sufficient=False` 且 `next_queries=[]` 时回退到首个子问题，并只在继续搜索时递增
  `iteration`。
- Writer 节点：`app/core/nodes.py` 提供异步 `writer_node()`，读取
  `app/core/prompts/writer.txt`，按 `requested_language` 生成最终报告，累加
  `total_tokens`，并通过报告中的 `[source_id]` 引用回填 `Citation.used_in_report`。
- LangGraph 执行图：`app/core/graph.py` 提供 `build_graph()` 和
  `route_after_critic()`，串联 planner -> searcher -> reader -> critic，并根据
  `max_iterations`、`TOKEN_BUDGET` 和 critic 决策进入 writer 或继续搜索。
- CLI：`scripts/run_cli.py` 提供本地轻量运行入口，构造完整 `ResearchState`，通过
  `build_graph()` 端到端运行研究流程，并将节点事件写入日志。
- 事件总线：`app/infra/cache.py` 提供异步 `publish()` 和 `subscribe()`，用于 session
  级 live 事件流；`subscribe()` 只负责 live 事件，不回放历史。
- SSE 事件生成器：`app/api/sse.py` 提供 `event_generator()`，采用“先订阅 live、再读取
  历史、再去重消费 live”的顺序，使用 `event_id` 作为断点游标。
- 数据库层：`app/infra/db.py` 使用 SQLAlchemy async，提供 session 创建、原子抢占启动、
  状态更新、事件持久化、历史事件回放和 citation 持久化接口。
- FastAPI API：`app/api/routes.py` 提供 `/health`、`/api/v1/research`、
  `/api/v1/research/{session_id}` 和 `/api/v1/research/stream/{session_id}`。
  POST 只创建 session；SSE 首次连接通过 `claim_session_start()` 启动 graph，重连只回放和订阅。
- Runner：`app/core/runner.py` 统一组装 initial state、调用 graph、处理超时和异常映射、
  更新 DB，并通过注入的 `emit_fn(event)` 发送 `done` 或 `error` 事件。
- Streamlit 前端：`frontend/app.py` 提供同步 `httpx` API 客户端和 SSE 客户端，
  可创建 session、实时展示事件、渲染最终报告，并在 sidebar 显示历史 session。

尚未完成：

- Docker 部署和项目收尾文档。

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

最小应用入口仍可用于验证配置加载：

```powershell
python -m app.main
```

本地研究流程可通过 CLI 运行：

```powershell
python scripts/run_cli.py "你的研究问题" --language zh --max-iterations 3
```

CLI 会直接调用 LangGraph 执行图。运行时需要可用的 `DEEPSEEK_API_KEY` 和
`TAVILY_API_KEY`，并会访问外部 LLM、搜索和网页抓取服务。

启动 API 服务：

```powershell
python -m app.main
```

创建研究 session：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/research" `
  -ContentType "application/json" `
  -Body '{"query":"如何验证研究 Agent 的网页来源？","language":"zh","max_iterations":3}'
```

随后连接返回的 `stream_url` 获取 SSE 事件；首次连接会启动 graph，重连不会重复启动。

启动前端：

```powershell
streamlit run frontend/app.py
```

前端默认连接 `http://localhost:8000`，可以通过环境变量覆盖：

```powershell
$env:EZ_AGENT_API_BASE_URL="http://localhost:8000"
streamlit run frontend/app.py
```

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

事件总线：

```python
from app.infra.cache import publish, subscribe

events = await subscribe("session-id")
await publish("session-id", {"event_id": 1, "type": "stage", "stage": "planning"})
event = await events.__anext__()
```

Planner 节点：

```python
from app.core.nodes import planner_node

result = await planner_node(initial_state)
sub_questions = result["sub_questions"]
```

Graph 调用：

```python
from app.core.graph import build_graph

graph = build_graph()
final_state = await graph.ainvoke(initial_state)
report = final_state["final_report"]
```

Runner 调用：

```python
from app.core.runner import run_research_cli

result = await run_research_cli(query="How do agents validate sources?")
```

## 测试

运行完整测试：

```powershell
pytest
```

当前阶段重点测试：

```powershell
pytest tests/test_config.py tests/test_tools.py tests/test_nodes.py tests/test_graph.py tests/test_api.py -v
```

如果 Windows 环境下 pytest 临时目录权限异常，可以指定仓库内临时目录：

```powershell
New-Item -ItemType Directory -Force -Path tmp_pytest
pytest -q -p no:cacheprovider --basetemp="C:\code\ez-agent\tmp_pytest\all"
```
