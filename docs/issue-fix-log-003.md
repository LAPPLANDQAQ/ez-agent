# 第三次项目问题修复日志

日期：2026-04-26

## 背景

本次修复围绕运行体验和前端体验展开。用户反馈：

- Streamlit 页面排版明显有问题，希望改成水墨风格
- `python -m app.main` 经常报 `WinError 10048`，项目看起来无法正常运行
- 手动查端口、启动 API、启动前端过于麻烦，希望项目改成一键启动

排查后确认：

- 默认 `8000` 和 `8501` 端口被旧 Python/Streamlit 进程占用，导致重复启动失败
- API 和前端在隔离端口上都可以正常启动，项目主逻辑没有损坏
- `scripts/check_env.py` 在 Windows GBK 控制台下会因为 emoji 输出触发 `UnicodeEncodeError`
- 前端原主题偏暗色科技风，流水线和按钮在部分宽度下容易显得拥挤

## 修复项

### 1. 增加一键启动入口

问题：

用户需要手动打开两个终端，并分别启动 API 与 Streamlit。端口被占用时还需要手动查 PID、
停止旧进程或修改端口，流程复杂且容易误判为项目不可用。

修复：

- 新增 `scripts/start_dev.py`
- 新增 Windows 双击入口 `start.bat`
- `Makefile` 增加 `make dev`
- README 改为优先推荐一键启动

启动器能力：

- 启动前加载配置，提前暴露 `.env` 问题
- 如果 `8000` 已有健康 API，则自动复用
- 如果默认端口被占用，则自动寻找后续可用端口
- 自动启动 Streamlit 并设置 `EZ_AGENT_API_BASE_URL`
- 自动打开浏览器
- `Ctrl+C` 时停止由启动器创建的子进程

### 2. 增加端口诊断脚本

问题：

`WinError 10048` 对普通使用者不直观。实际原因是端口被占用，但启动失败信息没有说明
哪个 PID 占用了端口。

修复：

- 新增 `scripts/check_ports.py`
- 默认检查 `API_PORT`/`8000` 和 `STREAMLIT_PORT`/`8501`
- 输出 `[OK]` 或 `[BUSY]`，并列出监听 PID
- README 增加端口诊断说明

### 3. 修复 Windows 控制台环境检查编码错误

问题：

`python scripts/check_env.py` 在部分 Windows 控制台中使用 GBK 输出，遇到 `✅`、`❌`、
`🎉` 等字符会抛出 `UnicodeEncodeError`，导致配置检查脚本本身失败。

修复：

- 将 emoji 输出替换为 ASCII 标记：
  - `[OK]`
  - `[WARN]`
  - `[ERROR]`

### 4. 前端改为水墨风格并修复排版

问题：

原前端视觉为暗色科技风，和用户期望不符；流水线连接线、按钮文本和卡片样式在部分布局下
容易显得拥挤。

修复：

- 重写 `frontend/styles.py`
- 使用宣纸底色、墨色文字、朱砂印章、青绿色状态色
- 移除外部字体依赖，优先使用系统中文衬线/宋体字体
- 流水线改为稳定的 5 列网格布局
- 阶段图标改为中文印章式文字
- 增加移动端响应式规则，避免卡片、事件日志和统计面板溢出

### 5. 文档更新

问题：

README 仍以手动 API/前端分别启动为主，不符合一键启动目标。

修复：

- README 的本地运行章节改为优先推荐 `start.bat` / `python scripts/start_dev.py`
- 保留手动启动方式作为调试备用
- 补充端口冲突和改端口说明

## 验证命令

```powershell
python scripts/check_env.py
python scripts/check_ports.py
python scripts/start_dev.py --no-browser --startup-timeout 20
python -m ruff check app scripts tests frontend
python -m mypy app scripts frontend
python -m pytest -p no:cacheprovider --basetemp=pytest_tmp
```

验证结果：

- 配置检查通过
- 启动器可以在 `8000`/`8501` 被占用时复用或自动换端口
- ruff 通过
- mypy 通过
- pytest 通过，58 个测试全绿

## 当前推荐启动方式

Windows 双击：

```text
start.bat
```

或命令行：

```powershell
python scripts/start_dev.py
```

启动后保持窗口打开即可。
