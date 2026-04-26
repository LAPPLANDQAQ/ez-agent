# 第二次项目问题修复日志

日期：2026-04-26

## 背景

本次排查在整合桌面目录前端文件之后进行。目标包括：

- 将根目录 `README.md` 与 `frontend/README.md` 整理为一份文档
- 再次审查项目代码、打包配置和前后端契约
- 修复发现的问题，并补充回归测试

基线检查：

- `ruff check app scripts tests frontend` 通过
- `pytest` 通过
- 新增执行 `mypy app scripts frontend`，发现静态类型和打包相关隐患

## 修复项

### 1. 两份 README 内容分散，容易后续分叉

问题：

根目录 `README.md` 覆盖了安装、运行、API、测试等主流程；`frontend/README.md`
单独描述前端结构、实时事件流、SSE 契约和设计令牌。两份文档都描述前端，长期维护时容易
出现配置变量、运行方式或接口契约不一致。

修复：

- 将前端结构、核心特性和前后端契约并入根目录 `README.md`
- 删除 `frontend/README.md`
- 在根 README 中保留 `EZ_AGENT_API_BASE_URL` 和兼容变量 `EZ_AGENT_API` 的说明

### 2. 历史会话详情缺少持久化引用

问题：

`GET /api/v1/research/{session_id}` 只返回 session 主表字段，不返回 `citation_records`。
前端打开历史会话时只能看到最终报告，看不到已持久化的引用面板，和实时完成态不一致。

修复：

- 新增 `app.infra.db.list_citations(session_id)`
- `get_research_session()` 返回详情时附带 `citations`
- `SessionDetail` schema 增加 `citations`
- 前端 `_open_session()` 将详情里的 citations 转换为 `CitationItem`

新增测试：

- `test_get_research_session_includes_citations`

### 3. SSE 客户端遇到异常 id 会中断解析

问题：

`frontend.api_client._parse_sse()` 直接对 `id:` 字段调用 `int()`。如果代理、调试服务或未来
非标准服务端发出非数字 id，前端会抛出 `ValueError` 并中断整个事件流。

修复：

- 新增 `_parse_event_id()`，无法解析时返回 `None`
- `_parse_sse()` 继续处理事件数据，不让单个异常 id 破坏流式连接

新增测试：

- `test_parse_sse_tolerates_malformed_event_id`

### 4. 打包配置漏掉 frontend 包

问题：

`pyproject.toml` 的 `tool.setuptools.packages.find.include` 只包含 `app*`。本地源码运行时
`frontend` 目录仍在 `sys.path` 下，所以不易暴露；但打包安装后 `frontend` 包不会进入
发行物，前端 Docker 或 wheel 部署存在隐患。

修复：

- 包发现规则改为 `include = ["app*", "frontend*"]`

### 5. wheel 构建可能漏掉 prompt 文本

问题：

核心节点通过 `Path(__file__).parent / "prompts"` 读取 prompt 文本。如果通过 wheel 形式
安装，`app/core/prompts/*.txt` 不一定被打包，运行时可能找不到 prompt 文件。

修复：

- 在 `pyproject.toml` 增加 `app.core` 的 package data：
  `prompts/*.txt`

### 6. mypy 暴露若干类型问题

问题：

`mypy app scripts frontend` 发现：

- `logger.py` 中 `Path()` 入参类型未被窄化
- SQLAlchemy async update 结果的 `rowcount` 类型不可见
- `tavily` 缺少类型标记
- `ChatOpenAI` 当前类型声明与运行参数存在差异

修复：

- `setup_file_sink()` 显式分支解析日志目录，避免 `None` 进入 `Path()`
- `claim_session_start()` 通过 `getattr(result, "rowcount", 0)` 读取影响行数
- `tavily` 导入处标注 `type: ignore[import-untyped]`
- `ChatOpenAI` 初始化参数先组装为 `dict[str, Any]`，避免第三方类型声明滞后影响项目检查

## 新增测试

- 历史会话详情包含按 `source_id` 排序的 citations
- 前端 SSE 解析器容忍非数字 `id`

## 验证命令

```powershell
ruff check app scripts tests frontend
mypy app scripts frontend
pytest -p no:cacheprovider --basetemp=pytest_tmp
```

验证结果：

- ruff 通过
- mypy 通过
- pytest 通过，58 个测试全绿

## 后续建议

- 在 CI 中增加 `mypy app scripts frontend`
- 若后续发布 wheel，增加一次 `pip install dist/*.whl` 后的 smoke test
- 为前端关键状态归约器继续补充事件回放测试，覆盖 done/error/历史打开场景
