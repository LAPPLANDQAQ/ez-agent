# ez-agent

`ez-agent` 是一个面向自动化深度研究场景的 Python Agent 项目。当前仓库按分阶段
commit 演进：配置与日志基础设施已经完成，工具层已经接入 LLM 客户端和 Tavily 搜索；
抓取、状态图、API、SSE、前端和部署仍会在后续 commit 中继续实现。

## 当前状态

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
- 领域模型：`app/domain/models.py` 已包含 `LLMResult` 和 `SearchResult`。

尚未完成：

- 网页抓取和缓存。
- LangGraph 状态、节点和完整执行图。
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

完整研究流程会在后续 graph、runner 和 API commit 中实现。

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

## 开发约定

- 每个阶段只提交对应 commit 范围内的文件。
- 不使用 `git add .`，避免把临时文件或本地指南误提交。
- 所有函数需要类型标注和简短 docstring。
- 业务代码中不直接使用 `print()`，CLI 最终输出和环境检查脚本除外。
- API Key 等敏感配置统一通过 `SecretStr.get_secret_value()` 读取。

## 当前推荐提交范围

如果正在提交搜索工具阶段，只提交：

```powershell
git add app/domain/models.py app/tools/search.py tests/test_tools.py
git commit -m "feat(tools): implement search tool with Tavily"
```

不要把本地开发指南、pytest 临时目录或其他无关文件加入该提交。
