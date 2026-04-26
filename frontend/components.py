"""可复用的 UI 组件。

每个组件接收快照（或快照子集），渲染对应区块。
组件无副作用、无 API 调用，便于纯渲染测试。
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from frontend.state import SessionSnapshot
from frontend.styles import STAGE_COLORS, STAGE_ORDER, TOKENS


# ----------------------------------------------------------------------
# 通用：HTML 注入辅助
# ----------------------------------------------------------------------

def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def card_open(title: str, badge: str | None = None) -> str:
    """生成卡片开头 HTML（需配合 card_close 使用）。"""
    badge_html = (
        f'<span class="ez-card-badge">{html.escape(badge)}</span>' if badge else ""
    )
    return f"""
<div class="ez-card">
  <div class="ez-card-header">
    <span class="ez-card-title">{html.escape(title)}</span>
    {badge_html}
  </div>
"""


def card_close() -> str:
    return "</div>"


# ----------------------------------------------------------------------
# 品牌
# ----------------------------------------------------------------------

def brand_header() -> None:
    html_block("""
<div class="ez-brand">
  <div class="ez-brand-mark">研</div>
  <div class="ez-brand-text">
    <span class="ez-brand-name">Ez Agent</span>
    <span class="ez-brand-tagline">水墨研究工作台</span>
  </div>
</div>
""")


def hero(title: str, subtitle: str) -> None:
    html_block(f"""
<div class="ez-hero">
  <div class="ez-hero-title">{html.escape(title)}</div>
  <div class="ez-hero-subtitle">{html.escape(subtitle)}</div>
</div>
""")


# ----------------------------------------------------------------------
# 状态徽章
# ----------------------------------------------------------------------

_STATUS_ZH = {
    "created": "待启动",
    "running": "进行中",
    "done": "已完成",
    "failed": "失败",
    "timeout": "超时",
}


def status_badge(status: str) -> str:
    """返回状态徽章 HTML 片段。"""
    label = _STATUS_ZH.get(status, status)
    return f'<span class="ez-badge {html.escape(status)}"><span class="ez-badge-dot"></span>{html.escape(label)}</span>'


# ----------------------------------------------------------------------
# 顶栏（活跃会话）
# ----------------------------------------------------------------------

def topbar(snap: SessionSnapshot) -> None:
    elapsed = snap.elapsed_seconds
    mm = int(elapsed // 60)
    ss = int(elapsed % 60)
    sid_short = snap.session_id[:8] if snap.session_id else "—"
    html_block(f"""
<div class="ez-topbar">
  <div class="ez-topbar-left">
    <div class="ez-topbar-query">{html.escape(snap.query)}</div>
    <div class="ez-topbar-meta">
      <span>SESSION {html.escape(sid_short)}</span>
      <span>•</span>
      <span>{mm:02d}:{ss:02d}</span>
      <span>•</span>
      <span>{html.escape(snap.language.upper())}</span>
    </div>
  </div>
  <div>{status_badge(snap.status)}</div>
</div>
""")


# ----------------------------------------------------------------------
# 流水线可视化
# ----------------------------------------------------------------------

def pipeline(snap: SessionSnapshot) -> None:
    """渲染五阶段流水线节点。

    状态规则：
      - 已完成：在 completed_stages 中
      - 进行中：current_stage
      - 待执行：其他
    """
    parts = ['<div class="ez-pipeline">']
    is_failed = snap.status in {"failed", "timeout"}

    for stage in STAGE_ORDER:
        info = STAGE_COLORS[stage]

        if stage in snap.completed_stages:
            cls = "complete"
            label_cls = "complete"
        elif snap.current_stage == stage:
            cls = "active"
            label_cls = "active"
        elif is_failed and snap.current_stage is None:
            # 失败终态：未完成阶段保持 pending（仅当前阶段曾活跃过会被错误化）
            cls = "pending"
            label_cls = ""
        else:
            cls = "pending"
            label_cls = ""

        parts.append(f"""
<div class="ez-stage">
  <div class="ez-stage-node {cls}">{info["icon"]}</div>
  <div class="ez-stage-label {label_cls}">{html.escape(info["label"])}</div>
</div>
""")

    parts.append("</div>")
    html_block(card_open("研究流水线") + "\n".join(parts) + card_close())


# ----------------------------------------------------------------------
# 统计面板
# ----------------------------------------------------------------------

def stats_panel(snap: SessionSnapshot, *, token_budget: int = 100_000) -> None:
    """渲染 tokens / 迭代 / 耗时 三宫格。"""
    tokens = snap.total_tokens
    pct = min(100, int(tokens / max(token_budget, 1) * 100))
    bar_class = "warning" if pct >= 80 else ""

    elapsed = snap.elapsed_seconds
    if elapsed >= 60:
        elapsed_str = f"{int(elapsed // 60)}<span class='ez-stat-unit'>m</span>{int(elapsed % 60)}<span class='ez-stat-unit'>s</span>"
    else:
        elapsed_str = f"{elapsed:.1f}<span class='ez-stat-unit'>s</span>"

    iter_str = f"{snap.iteration}<span class='ez-stat-unit'>/ {snap.max_iterations}</span>"

    iter_pct = int(snap.iteration / max(snap.max_iterations, 1) * 100)

    inner = f"""
<div class="ez-stat-grid">
  <div class="ez-stat">
    <div class="ez-stat-label">Tokens</div>
    <div class="ez-stat-value">{tokens:,}</div>
    <div class="ez-stat-bar"><div class="ez-stat-bar-fill {bar_class}" style="width: {pct}%"></div></div>
  </div>
  <div class="ez-stat">
    <div class="ez-stat-label">迭代轮次</div>
    <div class="ez-stat-value">{iter_str}</div>
    <div class="ez-stat-bar"><div class="ez-stat-bar-fill" style="width: {iter_pct}%"></div></div>
  </div>
  <div class="ez-stat">
    <div class="ez-stat-label">已运行</div>
    <div class="ez-stat-value">{elapsed_str}</div>
    <div class="ez-stat-bar"><div class="ez-stat-bar-fill" style="width: 0%"></div></div>
  </div>
</div>
"""
    html_block(card_open("运行指标") + inner + card_close())


# ----------------------------------------------------------------------
# 子问题列表
# ----------------------------------------------------------------------

def sub_questions_panel(snap: SessionSnapshot) -> None:
    if not snap.sub_questions:
        body = '<div class="ez-empty">规划阶段尚未产出子问题…</div>'
    else:
        items = "\n".join(
            f'<div class="ez-subq"><div class="ez-subq-num">{i+1:02d}</div>'
            f'<div class="ez-subq-text">{html.escape(q)}</div></div>'
            for i, q in enumerate(snap.sub_questions)
        )
        body = items
    badge = f"{len(snap.sub_questions)} 个" if snap.sub_questions else None
    html_block(card_open("子问题拆解", badge=badge) + body + card_close())


# ----------------------------------------------------------------------
# 来源列表
# ----------------------------------------------------------------------

_SOURCE_ICON = {
    "searching": "寻",
    "reading": "阅",
    "read": "录",
}


def sources_panel(snap: SessionSnapshot, *, max_show: int = 30) -> None:
    sources = list(snap.sources.values())
    if not sources:
        body = '<div class="ez-empty">尚无搜集到的来源…</div>'
    else:
        # read 在前，reading 次之，searching 最后
        order = {"read": 0, "reading": 1, "searching": 2}
        sources.sort(key=lambda s: order.get(s.state, 9))

        rows = []
        for src in sources[:max_show]:
            icon = _SOURCE_ICON.get(src.state, "源")
            rows.append(f"""
<div class="ez-source">
  <div class="ez-source-status">{icon}</div>
  <div class="ez-source-content">
    <div class="ez-source-title">{html.escape(src.title or "(无标题)")}</div>
    <div class="ez-source-url">{html.escape(src.url)}</div>
  </div>
</div>
""")
        body = "\n".join(rows)
        if len(sources) > max_show:
            body += f'<div class="ez-empty">还有 {len(sources) - max_show} 条来源未显示</div>'

    badge = f"{len(sources)} 条" if sources else None
    html_block(card_open("已发现的来源", badge=badge) + body + card_close())


# ----------------------------------------------------------------------
# 事件日志
# ----------------------------------------------------------------------

def event_log_panel(snap: SessionSnapshot, *, max_show: int = 200) -> None:
    if not snap.events:
        body = '<div class="ez-empty">等待事件流…</div>'
    else:
        # 倒序展示最新在前，但保留只取最后 N 条
        events = snap.events[-max_show:]
        rows = []
        for ev in events:
            t = _format_time(ev.timestamp)
            rows.append(f"""
<div class="ez-event {html.escape(ev.event_type)}">
  <div class="ez-event-time">{t}</div>
  <div class="ez-event-type">{html.escape(ev.event_type)}</div>
  <div class="ez-event-msg">{html.escape(ev.message)}</div>
</div>
""")
        body = f'<div class="ez-event-log">{"".join(rows)}</div>'

    badge = f"{len(snap.events)} 事件" if snap.events else None
    html_block(card_open("事件流", badge=badge) + body + card_close())


# ----------------------------------------------------------------------
# 最终报告
# ----------------------------------------------------------------------

def report_panel(snap: SessionSnapshot) -> None:
    if not snap.final_report:
        return

    # 顶部摘要条
    cit_used = sum(1 for c in snap.citations if c.used_in_report)
    cit_total = len(snap.citations)
    finish = snap.finish_reason or "completed"

    summary_html = f"""
<div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem;">
  <span class="ez-badge done"><span class="ez-badge-dot"></span>{html.escape(finish)}</span>
  <span class="ez-badge done"><span class="ez-badge-dot"></span>{cit_used}/{cit_total} 引用使用</span>
  <span class="ez-badge done"><span class="ez-badge-dot"></span>{snap.total_tokens:,} tokens</span>
  <span class="ez-badge done"><span class="ez-badge-dot"></span>{snap.iteration} 轮</span>
</div>
"""
    html_block(summary_html)

    # Streamlit 的 markdown 已支持代码高亮，但我们想要自定义样式：
    # 用一个外壳 div 包裹，再在内部交给 st.markdown 渲染 markdown
    html_block('<div class="ez-report">')
    st.markdown(snap.final_report)
    html_block("</div>")


def citations_panel(snap: SessionSnapshot) -> None:
    if not snap.citations:
        return
    rows = []
    for c in snap.citations:
        used_cls = "" if c.used_in_report else " unused"
        snippet = c.snippet[:200] + ("…" if len(c.snippet) > 200 else "")
        rows.append(f"""
<div class="ez-citation{used_cls}">
  <div class="ez-citation-id">[{c.source_id}]</div>
  <div class="ez-citation-body">
    <div class="ez-citation-title">{html.escape(c.title or "(无标题)")}</div>
    <div class="ez-citation-snippet">{html.escape(snippet)}</div>
    <a class="ez-citation-link" href="{html.escape(c.url)}" target="_blank" rel="noopener">{html.escape(c.url)}</a>
  </div>
</div>
""")
    used = sum(1 for c in snap.citations if c.used_in_report)
    badge = f"{used}/{len(snap.citations)} 使用"
    html_block(card_open("引用列表", badge=badge) + "\n".join(rows) + card_close())


# ----------------------------------------------------------------------
# 错误面板
# ----------------------------------------------------------------------

def error_panel(snap: SessionSnapshot) -> None:
    if snap.status not in {"failed", "timeout"}:
        return
    code = snap.error_code or "—"
    msg = snap.error_message or "未提供错误信息"
    color = TOKENS["seal"] if snap.status == "failed" else TOKENS["gold"]
    html_block(f"""
<div class="ez-card" style="border-color: {color}; background: rgba(163, 58, 43, 0.07);">
  <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
    <span style="font-size: 1.1rem; font-weight: 800;">!</span>
    <span style="font-weight: 700; color: {TOKENS['ink']};">研究终止 — {html.escape(code)}</span>
  </div>
  <div style="color: {TOKENS['ink_soft']}; font-size: 0.9rem; line-height: 1.5;">
    {html.escape(msg)}
  </div>
</div>
""")


# ----------------------------------------------------------------------
# 历史侧栏
# ----------------------------------------------------------------------

def history_item(
    item: dict[str, Any],
    *,
    is_active: bool = False,
) -> str:
    """渲染单条历史会话。返回 HTML，不直接 st.markdown。"""
    status = item.get("status", "created")
    query = item.get("query", "(无标题)")
    sid = item.get("session_id", "")
    created = item.get("created_at", "")[:16].replace("T", " ")
    tokens = item.get("total_tokens", 0)

    active_cls = " active" if is_active else ""
    return f"""
<div class="ez-history-item{active_cls}">
  <div class="ez-history-query">{html.escape(query)}</div>
  <div class="ez-history-meta">
    <span>{html.escape(created)}</span>
    {status_badge(status)}
  </div>
  <div class="ez-history-meta" style="margin-top: 4px;">
    <span style="font-family: 'JetBrains Mono', monospace;">{html.escape(sid[:8])}</span>
    <span>{tokens:,} tok</span>
  </div>
</div>
"""


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------

def _format_time(ts: float) -> str:
    import time
    return time.strftime("%H:%M:%S", time.localtime(ts))
