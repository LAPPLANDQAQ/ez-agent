"""Ez Agent — Streamlit 研究工作台。

关键设计：
1. **状态分离**：UI 状态（snapshot）由 SSE 事件归约而成，
   渲染只读取快照，永远不直接拼接事件；
2. **占位符流式渲染**：进入 running 态后用 `st.empty()` 在原地刷新
   各区块，而非整页 rerun，避免闪烁；
3. **重连游标**：snapshot.last_event_id 即 SSE Last-Event-ID，
   断网/页面刷新后能精确续接，无重复无遗漏（修正 11.4）；
4. **首连即启动**：仅 POST /research 创建会话，graph 由 SSE 端点
   原子抢占启动（修正 5）；前端直连 stream 即可。

环境变量：
    EZ_AGENT_API_BASE_URL / EZ_AGENT_API   后端 API 根 URL（默认 http://localhost:8000）

运行：
    streamlit run frontend/app.py
"""

from __future__ import annotations

import os
import time
from typing import Any

import streamlit as st

from frontend.api_client import ApiError, EzAgentClient
from frontend.components import (
    brand_header,
    citations_panel,
    error_panel,
    event_log_panel,
    hero,
    history_item,
    html_block,
    pipeline,
    report_panel,
    sources_panel,
    stats_panel,
    status_badge,
    sub_questions_panel,
    topbar,
)
from frontend.state import CitationItem, SessionSnapshot, reduce_event
from frontend.styles import main_css

# ----------------------------------------------------------------------
# 页面配置
# ----------------------------------------------------------------------

st.set_page_config(
    page_title="Ez Agent — Deep Research",
    page_icon="研",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(main_css(), unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 配置 & 客户端
# ----------------------------------------------------------------------

DEFAULT_API_URL = (
    os.getenv("EZ_AGENT_API_BASE_URL")
    or os.getenv("EZ_AGENT_API")
    or "http://localhost:8000"
)
TOKEN_BUDGET = int(os.getenv("EZ_AGENT_TOKEN_BUDGET", "100000"))


def get_client() -> EzAgentClient:
    base = st.session_state.get("api_url", DEFAULT_API_URL)
    return EzAgentClient(base)


# ----------------------------------------------------------------------
# Session state 初始化
# ----------------------------------------------------------------------

def init_state() -> None:
    ss = st.session_state
    ss.setdefault("api_url", DEFAULT_API_URL)
    ss.setdefault("snapshot", None)              # SessionSnapshot | None
    ss.setdefault("history", [])                  # list[dict]
    ss.setdefault("history_loaded_at", 0.0)
    ss.setdefault("language", "zh")
    ss.setdefault("max_iterations", 3)
    ss.setdefault("pending_query", None)          # 等待启动的查询
    ss.setdefault("query_input", "")
    ss.setdefault("api_status", "unknown")        # "ok" | "down" | "unknown"


# ----------------------------------------------------------------------
# 侧边栏
# ----------------------------------------------------------------------

def render_sidebar() -> None:
    with st.sidebar:
        brand_header()

        # ----- API 配置 -----
        with st.expander("后端连接", expanded=False):
            new_url = st.text_input(
                "API URL",
                value=st.session_state["api_url"],
                key="api_url_input",
                help="FastAPI 后端的根地址。",
            )
            if new_url != st.session_state["api_url"]:
                st.session_state["api_url"] = new_url
                st.session_state["api_status"] = "unknown"

            cols = st.columns([1, 1])
            with cols[0]:
                if st.button("探活", use_container_width=True, key="ping_btn"):
                    _ping_api()
            with cols[1]:
                if st.button("刷新历史", use_container_width=True, key="refresh_history"):
                    _load_history(force=True)

            status = st.session_state["api_status"]
            label = {"ok": "在线", "down": "离线", "unknown": "未探测"}[status]
            html_block(f'<div style="margin-top: 6px;">{status_badge("done" if status == "ok" else "failed" if status == "down" else "created")} {label}</div>')

        # ----- 新建研究按钮 -----
        if st.button(
            "新建研究",
            use_container_width=True,
            type="secondary",
            key="new_research_btn",
        ):
            st.session_state["snapshot"] = None
            st.session_state["pending_query"] = None
            st.rerun()

        st.markdown("###### 历史会话")

        # ----- 历史列表 -----
        if not st.session_state["history"]:
            _load_history(force=False)

        history = st.session_state["history"]
        active_sid = (
            st.session_state["snapshot"].session_id
            if st.session_state["snapshot"]
            else None
        )

        if not history:
            html_block('<div class="ez-empty">暂无历史会话</div>')
        else:
            for item in history[:30]:
                sid = item.get("session_id", "")
                with st.container():
                    html_block(history_item(item, is_active=sid == active_sid))
                    # streamlit 的 button 不能直接放进自定义 HTML 里，
                    # 用一个紧贴的隐形按钮承接点击
                    if st.button(
                        "查看",
                        key=f"hist_{sid}",
                        use_container_width=True,
                    ):
                        _open_session(sid)


# ----------------------------------------------------------------------
# 主区：空状态 / 活跃会话 / 终态
# ----------------------------------------------------------------------

def render_empty_state() -> None:
    """无活跃会话时的入口表单。"""
    hero(
        "Ez Agent",
        "以水墨卷轴呈现多 Agent 深度研究流程：拆解、检索、阅读、反思与成文。",
    )

    col_l, col_c, col_r = st.columns([1, 3, 1])
    with col_c:
        query = st.text_area(
            "研究问题",
            value=st.session_state.get("query_input", ""),
            placeholder="例如：2026 年 RAG 领域有哪些值得关注的新进展？请综述方法、代表工作和未解决问题。",
            height=120,
            label_visibility="collapsed",
            key="hero_query_input",
        )

        # 配置行
        cfg_cols = st.columns([2, 2, 3])
        with cfg_cols[0]:
            lang = st.selectbox(
                "语言",
                options=["zh", "en"],
                format_func=lambda x: "中文" if x == "zh" else "English",
                index=0 if st.session_state["language"] == "zh" else 1,
                key="lang_select",
            )
            st.session_state["language"] = lang

        with cfg_cols[1]:
            max_iter = st.slider(
                "最大迭代",
                min_value=1,
                max_value=5,
                value=st.session_state["max_iterations"],
                key="iter_slider",
                help="Critic 判定信息不足时最多追加几轮检索。",
            )
            st.session_state["max_iterations"] = max_iter

        with cfg_cols[2]:
            st.markdown(
                f"<div style='padding-top: 30px; color: #5F6E89; font-size: 0.85rem;'>"
                f"约束：{max_iter} 轮 · {TOKEN_BUDGET // 1000}k token 预算"
                f"</div>",
                unsafe_allow_html=True,
            )

        # 启动按钮
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        if st.button(
            "开始深度研究",
            use_container_width=True,
            type="primary",
            disabled=len(query.strip()) < 5,
            key="start_btn",
        ):
            st.session_state["pending_query"] = query.strip()
            st.rerun()

        # 示例查询
        st.markdown(
            '<div style="margin-top: 1.5rem; text-align: center; color: #5F6E89; font-size: 0.78rem; '
            'text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600;">推荐起点</div>',
            unsafe_allow_html=True,
        )

        examples = [
            "2026 年 RAG 领域有哪些新进展？",
            "对比主流 LLM Agent 框架的设计哲学",
            "Mamba 架构相比 Transformer 的实际优势？",
            "AI 编程工具 2026 年的演化路径",
        ]
        ex_cols = st.columns(len(examples))
        for col, ex in zip(ex_cols, examples):
            with col:
                if st.button(ex, key=f"ex_{ex[:8]}", use_container_width=True):
                    st.session_state["query_input"] = ex
                    st.rerun()


def render_session_view(snap: SessionSnapshot) -> dict[str, Any]:
    """渲染活跃/历史会话的主区。

    返回各区块的 placeholder 字典，便于流式更新时原地刷新。
    """
    placeholders: dict[str, Any] = {}

    placeholders["topbar"] = st.empty()
    with placeholders["topbar"].container():
        topbar(snap)

    # 主网格：左 8 / 右 4
    left, right = st.columns([8, 4], gap="medium")

    with left:
        placeholders["pipeline"] = st.empty()
        with placeholders["pipeline"].container():
            pipeline(snap)

        placeholders["error"] = st.empty()
        with placeholders["error"].container():
            error_panel(snap)

        placeholders["report"] = st.empty()
        with placeholders["report"].container():
            report_panel(snap)
            citations_panel(snap)

        placeholders["events"] = st.empty()
        with placeholders["events"].container():
            event_log_panel(snap)

    with right:
        placeholders["stats"] = st.empty()
        with placeholders["stats"].container():
            stats_panel(snap, token_budget=TOKEN_BUDGET)

        placeholders["sub_q"] = st.empty()
        with placeholders["sub_q"].container():
            sub_questions_panel(snap)

        placeholders["sources"] = st.empty()
        with placeholders["sources"].container():
            sources_panel(snap)

    return placeholders


def refresh_view(snap: SessionSnapshot, placeholders: dict[str, Any]) -> None:
    """流式过程中：用最新快照刷新所有占位符。"""
    with placeholders["topbar"].container():
        topbar(snap)
    with placeholders["pipeline"].container():
        pipeline(snap)
    with placeholders["error"].container():
        error_panel(snap)
    with placeholders["stats"].container():
        stats_panel(snap, token_budget=TOKEN_BUDGET)
    with placeholders["sub_q"].container():
        sub_questions_panel(snap)
    with placeholders["sources"].container():
        sources_panel(snap)
    with placeholders["events"].container():
        event_log_panel(snap)
    with placeholders["report"].container():
        report_panel(snap)
        citations_panel(snap)


# ----------------------------------------------------------------------
# 流式驱动
# ----------------------------------------------------------------------

def drive_stream(snap: SessionSnapshot, placeholders: dict[str, Any]) -> None:
    """连接 SSE，逐事件归约 + 刷新 UI。

    遵循修正 11.4 算法：
      - 服务端先发历史事件再发 live；
      - 我们以 last_event_id 去重（snapshot.last_event_id）；
      - 终态事件（done/error）出现后退出循环。
    """
    client = get_client()
    last_render = 0.0
    RENDER_THROTTLE = 0.12   # 每 120ms 至多刷一次，缓解高频事件抖动

    try:
        for event in client.stream_events(
            snap.session_id,
            last_event_id=snap.last_event_id,
        ):
            eid = event.get("event_id")
            # 去重：服务端可能在历史回放与 live 接续处发同一条事件
            if eid is not None and eid <= snap.last_event_id:
                continue

            reduce_event(snap, event)

            now = time.time()
            if now - last_render >= RENDER_THROTTLE or snap.is_terminal:
                refresh_view(snap, placeholders)
                last_render = now

            if snap.is_terminal:
                break

    except ApiError as exc:
        snap.status = "failed"
        snap.error_code = "FRONTEND"
        snap.error_message = f"SSE 连接失败：{exc}"
        snap.ended_at = time.time()
        refresh_view(snap, placeholders)


# ----------------------------------------------------------------------
# 行为：启动 / 打开历史会话
# ----------------------------------------------------------------------

def _start_research(query: str) -> None:
    """POST /research 创建会话，写入 snapshot，进入流式态。"""
    client = get_client()
    try:
        result = client.create_research(
            query,
            language=st.session_state["language"],
            max_iterations=st.session_state["max_iterations"],
        )
    except ApiError as exc:
        st.error(f"创建研究会话失败：{exc}")
        st.session_state["pending_query"] = None
        return

    snap = SessionSnapshot(
        session_id=result["session_id"],
        query=query,
        language=st.session_state["language"],
        max_iterations=st.session_state["max_iterations"],
        status="created",
        started_at=time.time(),
    )
    st.session_state["snapshot"] = snap
    st.session_state["pending_query"] = None


def _open_session(session_id: str) -> None:
    """打开历史会话：拉详情 + 全量事件回放。"""
    client = get_client()
    try:
        detail = client.get_session(session_id)
    except ApiError as exc:
        st.error(f"加载会话失败：{exc}")
        return

    if detail is None:
        st.warning(f"会话 {session_id[:8]} 已不存在")
        return

    snap = SessionSnapshot(
        session_id=session_id,
        query=detail.get("query", ""),
        language=detail.get("requested_language", "zh"),
        max_iterations=detail.get("max_iterations", 3),
        status=detail.get("status", "done"),
        total_tokens=detail.get("total_tokens", 0),
        iteration=detail.get("iteration_count", 0),
        final_report=detail.get("final_report"),
        error_message=detail.get("error_message"),
        started_at=time.time(),  # 用本地时间作为 ui clock
        ended_at=time.time() if detail.get("status") in {"done", "failed", "timeout"} else None,
    )
    snap.citations = [
        CitationItem(
            source_id=int(citation.get("source_id", 0)),
            url=str(citation.get("url", "")),
            title=str(citation.get("title", "")),
            snippet=str(citation.get("snippet", "")),
            used_in_report=bool(citation.get("used_in_report", False)),
        )
        for citation in detail.get("citations", [])
        if isinstance(citation, dict)
    ]
    st.session_state["snapshot"] = snap
    st.rerun()


def _ping_api() -> None:
    try:
        get_client().health()
        st.session_state["api_status"] = "ok"
    except ApiError:
        st.session_state["api_status"] = "down"


def _load_history(*, force: bool) -> None:
    now = time.time()
    if not force and now - st.session_state.get("history_loaded_at", 0.0) < 5.0:
        return
    try:
        items = get_client().list_sessions(limit=30)
        st.session_state["history"] = items
        st.session_state["history_loaded_at"] = now
        st.session_state["api_status"] = "ok"
    except ApiError:
        st.session_state["history"] = []
        st.session_state["api_status"] = "down"


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def main() -> None:
    init_state()
    render_sidebar()

    # 1) 处理待启动的查询
    pending = st.session_state.get("pending_query")
    if pending:
        _start_research(pending)
        # 不 rerun：当前 run 直接进入流式驱动

    snap: SessionSnapshot | None = st.session_state.get("snapshot")

    # 2) 空状态
    if snap is None:
        render_empty_state()
        return

    # 3) 渲染会话视图
    placeholders = render_session_view(snap)

    # 4) 若非终态，进入 SSE 驱动
    if not snap.is_terminal:
        drive_stream(snap, placeholders)
        # 流结束后再渲染一次确保最终态生效
        refresh_view(snap, placeholders)
        # 终态后异步刷新历史列表（下次 sidebar 渲染会用到）
        st.session_state["history_loaded_at"] = 0.0


if __name__ == "__main__":
    main()
