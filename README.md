# ez-agent

`ez-agent` 是一个面向智能体项目的 Python 初始骨架。当前仓库提供了可直接上传的目录布局、最小可运行入口，以及面向核心流程、工具适配、基础设施和 API 的占位模块。

## 项目用途

- 保持第一次提交足够小、干净，并便于后续扩展。
- 从一开始就把智能体逻辑、工具适配层、基础设施和 API 代码拆开。
- 为后续的规划、执行、评估和前端集成预留清晰基础。

## 目录结构

```text
ez-agent/
+-- app/
|   +-- api/
|   +-- core/
|   |   +-- prompts/
|   +-- infra/
|   +-- tools/
|   +-- config.py
|   +-- main.py
+-- frontend/
+-- scripts/
+-- tests/
+-- .env.example
+-- .gitignore
+-- Makefile
+-- pyproject.toml
+-- README.md
```

## 依赖安装

建议先创建虚拟环境，再安装项目依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

### 中国大陆用户：使用清华镜像源

如果默认安装速度慢，或经常遇到超时，可以直接使用清华 PyPI 镜像：

```powershell
pip install -e .[dev] -i https://pypi.tuna.tsinghua.edu.cn/simple
```

如果你希望长期使用清华镜像，可以执行：

```powershell
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

恢复为官方源：

```powershell
pip config unset global.index-url
```

## 快速开始

```powershell
python -m app.main
```

或者：

```powershell
python scripts/run_cli.py
```

## 后续计划

- 接入真实的 LLM、搜索和抓取能力。
- 完善智能体图结构与状态流转。
- 增加 HTTP API 和流式响应能力。
- 扩展测试与开发工具链。
- 补齐前端交互流程。
