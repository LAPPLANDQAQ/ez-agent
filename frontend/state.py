"""会话快照与事件归约器。

每条 SSE 事件按类型 fold 进 `SessionSnapshot`，UI 只渲染快照，
不直接依赖事件流，从而：
  - 历史回放与 live 事件走完全相同的路径；
  - 任意时刻的 rerun 都能从 events 列表重放出当前快照；
  - 测试可直接喂事件验证状态机。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------

ALL_STAGES = ["planning", "searching", "reading", "criticizing", "writing"]


# ----------------------------------------------------------------------
# 快照
# ----------------------------------------------------------------------

@dataclass
class SourceItem:
    url: str
    title: str
    source_id: int = 0
    state: Literal["searching", "reading", "read"] = "searching"


@dataclass
class CitationItem:
    source_id: int
    url: str
    title: str
    snippet: str = ""
    used_in_report: bool = False


@dataclass
class EventLogItem:
    event_id: int | None
    event_type: str
    timestamp: float
    message: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionSnapshot:
    """前端持有的会话状态。"""

    session_id: str
    query: str
    language: Literal["zh", "en"] = "zh"
    max_iterations: int = 3

    status: Literal["created", "running", "done", "failed", "timeout"] = "created"
    current_stage: str | None = None
    completed_stages: set[str] = field(default_factory=set)

    sub_questions: list[str] = field(default_factory=list)
    sources: dict[str, SourceItem] = field(default_factory=dict)  # url -> SourceItem

    iteration: int = 0
    total_tokens: int = 0

    final_report: str | None = None
    citations: list[CitationItem] = field(default_factory=list)
    finish_reason: str | None = None

    error_code: str | None = None
    error_message: str | None = None

    events: list[EventLogItem] = field(default_factory=list)
    last_event_id: int = 0

    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    # ------------------------------------------------------------------
    # 计算属性
    # ------------------------------------------------------------------
    @property
    def elapsed_seconds(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.time()
        return max(0.0, end - self.started_at)

    @property
    def is_terminal(self) -> bool:
        return self.status in {"done", "failed", "timeout"}


# ----------------------------------------------------------------------
# 归约器
# ----------------------------------------------------------------------

# 后端 event 名 -> 中文动作描述（用于事件流摘要）
_STAGE_ZH = {
    "planning":     "进入规划阶段",
    "searching":    "进入检索阶段",
    "reading":      "进入阅读阶段",
    "criticizing":  "进入反思阶段",
    "writing":      "进入写作阶段",
}


def reduce_event(snapshot: SessionSnapshot, event: dict[str, Any]) -> SessionSnapshot:
    """把单条 SSE 事件折叠进 snapshot，返回更新后的 snapshot。

    本函数原地修改 snapshot 并返回（dataclass 引用语义），
    调用方按需 deepcopy。修正 11.4 的去重在外部完成，进入此处的
    每条事件都已是"应当被处理"的事件。
    """
    etype = event.get("type", "message")
    data = event.get("data", {}) or {}
    eid = event.get("event_id")

    # 1) 通用：维护 last_event_id 与 events 日志
    if eid is not None and eid > snapshot.last_event_id:
        snapshot.last_event_id = eid

    snapshot.events.append(
        EventLogItem(
            event_id=eid,
            event_type=etype,
            timestamp=time.time(),
            message=_summarize(etype, data),
            raw=data,
        )
    )

    # 2) 按类型分支
    if etype == "stage":
        stage = data.get("stage")
        if stage in ALL_STAGES:
            # 进入新阶段时，把之前所有阶段标记为已完成
            if snapshot.current_stage and snapshot.current_stage != stage:
                snapshot.completed_stages.add(snapshot.current_stage)
            snapshot.current_stage = stage
            snapshot.status = "running"

    elif etype == "sub_questions":
        questions = data.get("questions") or []
        if isinstance(questions, list):
            snapshot.sub_questions = [str(q) for q in questions]

    elif etype == "searching":
        # 单条搜索开始 - 只记录 iteration（如果有）
        if "iteration" in data:
            try:
                snapshot.iteration = max(snapshot.iteration, int(data["iteration"]))
            except (TypeError, ValueError):
                pass

    elif etype == "reading":
        url = data.get("url")
        title = data.get("title", "") or url or ""
        if url:
            existing = snapshot.sources.get(url)
            if existing:
                existing.state = "reading"
                if title and not existing.title:
                    existing.title = title
            else:
                snapshot.sources[url] = SourceItem(
                    url=url,
                    title=title or _short_url(url),
                    state="reading",
                )

    elif etype == "critic":
        if "iteration" in data:
            try:
                snapshot.iteration = max(snapshot.iteration, int(data["iteration"]))
            except (TypeError, ValueError):
                pass
        # 标记当前已读取的所有 reading 状态来源为 read
        for src in snapshot.sources.values():
            if src.state == "reading":
                src.state = "read"

    elif etype == "writing":
        # 写作开始，仅作为日志事件展示
        pass

    elif etype == "done":
        snapshot.completed_stages.update(ALL_STAGES)
        snapshot.current_stage = None
        snapshot.status = "done"
        snapshot.ended_at = time.time()
        snapshot.final_report = data.get("report") or data.get("final_report")

        cits_raw = data.get("citations") or []
        snapshot.citations = [
            CitationItem(
                source_id=int(c.get("source_id", 0)),
                url=c.get("url", ""),
                title=c.get("title", "") or _short_url(c.get("url", "")),
                snippet=c.get("snippet", ""),
                used_in_report=bool(c.get("used_in_report", False)),
            )
            for c in cits_raw
            if isinstance(c, dict)
        ]
        # 按 source_id 升序
        snapshot.citations.sort(key=lambda c: c.source_id)

        stats = data.get("stats") or {}
        if isinstance(stats, dict):
            tt = stats.get("total_tokens")
            if tt is not None:
                try:
                    snapshot.total_tokens = int(tt)
                except (TypeError, ValueError):
                    pass
            it = stats.get("iteration_count") or stats.get("iterations")
            if it is not None:
                try:
                    snapshot.iteration = int(it)
                except (TypeError, ValueError):
                    pass
            snapshot.finish_reason = stats.get("finish_reason")

    elif etype == "error":
        snapshot.status = "failed"
        # E4002 实际是 timeout
        code = data.get("code", "") or ""
        if code == "E4002":
            snapshot.status = "timeout"
        snapshot.error_code = code or None
        snapshot.error_message = data.get("message") or "未知错误"
        snapshot.ended_at = time.time()
        snapshot.current_stage = None

    return snapshot


# ----------------------------------------------------------------------
# 辅助
# ----------------------------------------------------------------------

def _summarize(etype: str, data: dict[str, Any]) -> str:
    """生成事件单行摘要，用于事件日志组件。"""
    if etype == "stage":
        stage = data.get("stage", "?")
        msg = data.get("message")
        zh = _STAGE_ZH.get(stage, stage)
        return f"{zh}" + (f" — {msg}" if msg else "")

    if etype == "sub_questions":
        n = len(data.get("questions") or [])
        return f"拆解出 {n} 个子问题"

    if etype == "searching":
        q = data.get("query", "")
        it = data.get("iteration")
        prefix = f"[轮次 {it}] " if it is not None else ""
        return f"{prefix}检索：{q}"

    if etype == "reading":
        title = data.get("title") or _short_url(data.get("url", ""))
        return f"读取：{title}"

    if etype == "critic":
        suff = data.get("sufficient")
        miss = data.get("missing") or []
        if suff:
            return "评估：信息充足，进入写作"
        nq = data.get("next_queries") or []
        return f"评估：信息不足（缺 {len(miss)} 项），追加 {len(nq)} 个查询"

    if etype == "writing":
        return data.get("message") or "开始撰写报告"

    if etype == "done":
        stats = data.get("stats") or {}
        reason = stats.get("finish_reason") or "completed"
        return f"研究完成（{reason}）"

    if etype == "error":
        code = data.get("code", "?")
        msg = data.get("message", "")
        return f"错误 {code}：{msg}"

    return f"事件 {etype}"


def _short_url(url: str) -> str:
    """域名 + 截断路径。"""
    if not url:
        return "未知来源"
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path.rstrip("/")
        return f"{p.netloc}{path[:40]}" if path else p.netloc
    except (ValueError, AttributeError):
        return url[:50]
