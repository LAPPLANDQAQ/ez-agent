# 第一次项目问题修复日志

日期：2026-04-26

## 背景

本次排查在 `develop` 分支完成。基础检查结果显示：

- `ruff check app scripts tests frontend` 通过
- `pytest -v` 通过
- 工作区存在未跟踪的本地参考文件 `EZ_AGENT_CODEX_GUIDE_TRUE_FINAL.md`

排查后优先处理高风险和中风险问题，目标是避免错误会话被误判为成功、提升 Docker
启动稳定性，并降低长时间运行和多进程部署风险。

## 修复项

### 1. 搜索全部失败被误判为正常完成

问题：

`search_multiple()` 对单个查询失败做了降级跳过，但当所有查询都失败时仍返回空列表。
这会让 graph 继续进入后续节点，最终可能以 `done` 结束，无法触发约定的 `E3001`。

修复：

- 新增 `app/domain/errors.py`
- 新增 `SearchProviderError`
- `search_multiple()` 在所有非空查询都失败时抛出 `SearchProviderError`
- `runner.py` 将 `SearchProviderError` 映射为 `E3001`

### 2. 网页抓取全部失败被误判为正常完成

问题：

`fetch_and_summarize_batch()` 对单个 URL 失败做了跳过，但当所有目标都失败时仍返回空
结果。后续 writer 可能在无证据情况下生成报告，并以成功状态结束，无法触发 `E3002`。

修复：

- 新增 `FetchProviderError`
- `fetch_and_summarize_batch()` 在所有目标都失败时抛出 `FetchProviderError`
- `runner.py` 将 `FetchProviderError` 映射为 `E3002`

### 3. SSE live 事件总线只能在单进程内工作

问题：

原 live bus 使用进程内 `_subscribers` 字典。单进程本地开发可用，但多 worker 或多副本
部署时，发布事件和 SSE 连接可能落在不同进程，导致实时事件丢失。

修复：

- `publish()` 优先通过 Redis pub/sub 发布事件
- `subscribe()` 优先订阅 Redis channel
- Redis 不可用时保留进程内队列作为本地开发回退

### 4. 已完成 research task 未从应用注册表清理

问题：

SSE 首次连接启动 graph 后会把 task 保存到 `app.state.research_tasks`，但 task 完成后
不会移除。长时间运行后注册表会随 session 数持续增长。

修复：

- 在 `stream_research_session()` 中为 task 添加 `done_callback`
- task 完成后从 `app.state.research_tasks` 删除对应 session

### 5. Docker API 容器可能早于数据库 ready

问题：

`docker-compose.yml` 只使用普通 `depends_on`，无法保证 Postgres 已经可接受连接。API
启动时会执行 `init_db()`，数据库尚未 ready 时可能启动失败。

修复：

- 为 Postgres 增加 `pg_isready` healthcheck
- 为 Redis 增加 `redis-cli ping` healthcheck
- API 使用 `depends_on.condition: service_healthy`

### 6. 本地运行产生的数据库和 egg-info 文件容易误入工作区

问题：

默认 SQLite 路径为 `research.db`，本地安装还可能生成 `*.egg-info/`。这些属于生成产物，
不应进入版本控制。

修复：

- `.gitignore` 增加 `research.db`
- `.gitignore` 增加 `*.db`、`*.sqlite`、`*.sqlite3`
- `.gitignore` 增加 `*.egg-info/`

## 新增测试

- 搜索全部失败时抛出 `SearchProviderError`
- 抓取全部失败时抛出 `FetchProviderError`
- runner 将 provider 错误映射为 `E3001` / `E3002`
- research task 完成后从 `app.state.research_tasks` 清理

## 验证命令

```powershell
ruff check app scripts tests frontend
python -m compileall app scripts tests frontend
pytest -v
```

## 后续建议

- 将 Docker compose 配置检查纳入有 Docker 的 CI 环境
- 为 mypy 增加项目级配置，避免 `frontend/app.py` 与 `app/` 包名冲突导致类型检查失败
- 根据生产部署规模决定是否进一步抽象事件总线，支持 Redis Stream 或持久化消息队列
