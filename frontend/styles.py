"""Ink-wash visual system for the Streamlit workspace."""

from __future__ import annotations

TOKENS = {
    "paper": "#f7f1e5",
    "paper_warm": "#efe4d1",
    "paper_deep": "#e5d4b8",
    "ink": "#1f2421",
    "ink_soft": "#4c554f",
    "ink_faint": "#7c867e",
    "line": "#cbb996",
    "line_soft": "rgba(112, 96, 65, 0.20)",
    "wash": "rgba(48, 64, 55, 0.08)",
    "wash_strong": "rgba(48, 64, 55, 0.16)",
    "jade": "#2f6f5e",
    "jade_soft": "#dbe8df",
    "seal": "#a33a2b",
    "seal_soft": "#f0d4c8",
    "gold": "#9b713d",
    "white": "#fffaf0",
}

STAGE_COLORS = {
    "planning": {"icon": "策", "color": TOKENS["jade"], "label": "拆解规划"},
    "searching": {"icon": "搜", "color": TOKENS["gold"], "label": "并发检索"},
    "reading": {"icon": "读", "color": TOKENS["jade"], "label": "深度阅读"},
    "criticizing": {"icon": "评", "color": TOKENS["seal"], "label": "反思评估"},
    "writing": {"icon": "文", "color": TOKENS["jade"], "label": "生成报告"},
}

STAGE_ORDER = ["planning", "searching", "reading", "criticizing", "writing"]


def main_css() -> str:
    """Return the global Streamlit CSS for the ink-wash interface."""
    t = TOKENS
    return f"""
<style>
#MainMenu, footer, header[data-testid="stHeader"] {{
    visibility: hidden;
    height: 0;
}}

html, body, [class*="st-"], .stMarkdown, .stTextInput, .stTextArea, .stButton {{
    font-family:
        "Noto Serif SC", "Songti SC", "SimSun", "Microsoft YaHei",
        "Segoe UI", serif !important;
    letter-spacing: 0 !important;
}}

code, pre, .stCode, .ez-event, .ez-source-url, .ez-topbar-meta {{
    font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace !important;
}}

.stApp {{
    color: {t["ink"]};
    background:
        radial-gradient(circle at 12% 8%, rgba(163, 58, 43, 0.08), transparent 18rem),
        radial-gradient(circle at 82% 14%, rgba(47, 111, 94, 0.10), transparent 20rem),
        radial-gradient(circle at 48% 92%, rgba(155, 113, 61, 0.09), transparent 24rem),
        linear-gradient(135deg, rgba(255, 250, 240, 0.86), rgba(239, 228, 209, 0.92)),
        {t["paper"]};
}}

.stApp::before {{
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    opacity: 0.42;
    background-image:
        linear-gradient(90deg, rgba(82, 63, 36, 0.035) 1px, transparent 1px),
        linear-gradient(rgba(82, 63, 36, 0.028) 1px, transparent 1px);
    background-size: 28px 28px;
    mix-blend-mode: multiply;
}}

.stApp > div {{
    position: relative;
    z-index: 1;
}}

.block-container {{
    max-width: 1280px !important;
    padding-top: 1rem !important;
    padding-bottom: 3rem !important;
}}

section[data-testid="stSidebar"] {{
    background:
        linear-gradient(180deg, rgba(255, 250, 240, 0.96), rgba(233, 218, 190, 0.96)),
        {t["paper_warm"]};
    border-right: 1px solid {t["line"]};
    box-shadow: 10px 0 32px rgba(61, 45, 24, 0.08);
}}

section[data-testid="stSidebar"] > div {{
    padding-top: 1.15rem;
}}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p {{
    color: {t["ink"]} !important;
}}

.ez-brand {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.15rem 0 1rem;
    border-bottom: 1px solid {t["line_soft"]};
    margin-bottom: 1rem;
}}

.ez-brand-mark {{
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 4px;
    color: {t["white"]};
    background:
        linear-gradient(145deg, rgba(187, 67, 48, 0.98), rgba(124, 31, 25, 0.98));
    border: 1px solid rgba(91, 20, 17, 0.55);
    box-shadow: 0 8px 20px rgba(92, 37, 26, 0.20);
    font-size: 1.35rem;
    font-weight: 800;
    line-height: 1;
}}

.ez-brand-name {{
    display: block;
    color: {t["ink"]};
    font-size: 1.12rem;
    font-weight: 800;
    line-height: 1.2;
}}

.ez-brand-tagline {{
    display: block;
    color: {t["ink_faint"]};
    font-size: 0.72rem;
    line-height: 1.4;
}}

.ez-hero {{
    position: relative;
    padding: 2.2rem 1rem 1.45rem;
    text-align: center;
}}

.ez-hero::before {{
    content: "";
    position: absolute;
    top: 0.7rem;
    left: 50%;
    width: min(540px, 76vw);
    height: 150px;
    transform: translateX(-50%);
    border-radius: 999px;
    background:
        radial-gradient(ellipse at 32% 48%, rgba(31, 36, 33, 0.16), transparent 58%),
        radial-gradient(ellipse at 66% 45%, rgba(47, 111, 94, 0.10), transparent 60%);
    filter: blur(18px);
    opacity: 0.72;
    z-index: -1;
}}

.ez-hero-title {{
    color: {t["ink"]};
    font-size: clamp(2.2rem, 6vw, 4rem);
    font-weight: 800;
    line-height: 1.08;
    margin-bottom: 0.75rem;
}}

.ez-hero-title::after {{
    content: "";
    display: block;
    width: 9rem;
    height: 4px;
    margin: 0.8rem auto 0;
    border-radius: 999px;
    background: linear-gradient(90deg, transparent, {t["seal"]}, transparent);
    opacity: 0.75;
}}

.ez-hero-subtitle {{
    max-width: 680px;
    margin: 0 auto;
    color: {t["ink_soft"]};
    font-size: 1rem;
    line-height: 1.8;
}}

.ez-card {{
    position: relative;
    overflow: hidden;
    background:
        linear-gradient(180deg, rgba(255, 250, 240, 0.84), rgba(247, 241, 229, 0.92)),
        {t["paper"]};
    border: 1px solid {t["line"]};
    border-radius: 8px;
    box-shadow:
        0 12px 30px rgba(61, 45, 24, 0.07),
        inset 0 0 0 1px rgba(255, 255, 255, 0.35);
    padding: 1.05rem 1.15rem;
    margin-bottom: 1rem;
}}

.ez-card::before {{
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
        radial-gradient(circle at 12% 4%, rgba(31, 36, 33, 0.05), transparent 11rem),
        radial-gradient(circle at 94% 100%, rgba(47, 111, 94, 0.055), transparent 12rem);
}}

.ez-card > * {{
    position: relative;
    z-index: 1;
}}

.ez-card-header {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-height: 1.8rem;
    padding-bottom: 0.7rem;
    margin-bottom: 0.9rem;
    border-bottom: 1px solid {t["line_soft"]};
}}

.ez-card-title {{
    color: {t["ink"]};
    font-size: 0.92rem;
    font-weight: 800;
    letter-spacing: 0 !important;
}}

.ez-card-title::before {{
    content: "";
    display: inline-block;
    width: 0.55rem;
    height: 0.55rem;
    margin-right: 0.45rem;
    border-radius: 50%;
    background: {t["seal"]};
    box-shadow: 0 0 0 4px rgba(163, 58, 43, 0.10);
    vertical-align: 0.05rem;
}}

.ez-card-badge {{
    margin-left: auto;
    color: {t["jade"]};
    background: rgba(47, 111, 94, 0.10);
    border: 1px solid rgba(47, 111, 94, 0.22);
    border-radius: 999px;
    padding: 0.16rem 0.55rem;
    font-size: 0.72rem;
    font-weight: 700;
}}

.ez-pipeline {{
    position: relative;
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.6rem;
    padding: 0.45rem 0.15rem 0.1rem;
}}

.ez-pipeline::before {{
    content: "";
    position: absolute;
    left: 9%;
    right: 9%;
    top: 1.75rem;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(31, 36, 33, 0.30), transparent);
}}

.ez-stage {{
    position: relative;
    display: grid;
    justify-items: center;
    gap: 0.55rem;
    min-width: 0;
}}

.ez-stage-node {{
    width: 3rem;
    height: 3rem;
    display: grid;
    place-items: center;
    border-radius: 50%;
    color: {t["ink_soft"]};
    background: {t["paper_warm"]};
    border: 1px solid {t["line"]};
    box-shadow: 0 5px 16px rgba(61, 45, 24, 0.08);
    font-size: 1rem;
    font-weight: 800;
}}

.ez-stage-node.active {{
    color: {t["white"]};
    background:
        radial-gradient(circle at 34% 28%, rgba(255,255,255,0.22), transparent 36%),
        {t["jade"]};
    border-color: rgba(47, 111, 94, 0.55);
    box-shadow:
        0 0 0 5px rgba(47, 111, 94, 0.12),
        0 10px 24px rgba(47, 111, 94, 0.22);
}}

.ez-stage-node.complete {{
    color: {t["white"]};
    background: {t["ink"]};
    border-color: rgba(31, 36, 33, 0.75);
}}

.ez-stage-label {{
    width: 100%;
    color: {t["ink_faint"]};
    font-size: 0.78rem;
    font-weight: 700;
    line-height: 1.35;
    text-align: center;
    overflow-wrap: anywhere;
}}

.ez-stage-label.active {{
    color: {t["jade"]};
}}

.ez-stage-label.complete {{
    color: {t["ink"]};
}}

.ez-stat-grid {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.65rem;
}}

.ez-stat {{
    min-width: 0;
    background: rgba(255, 250, 240, 0.52);
    border: 1px solid {t["line_soft"]};
    border-radius: 8px;
    padding: 0.75rem 0.78rem;
}}

.ez-stat-label {{
    color: {t["ink_faint"]};
    font-size: 0.72rem;
    font-weight: 700;
    margin-bottom: 0.42rem;
}}

.ez-stat-value {{
    color: {t["ink"]};
    font-size: clamp(1.1rem, 2.2vw, 1.55rem);
    font-weight: 800;
    line-height: 1.05;
    font-variant-numeric: tabular-nums;
    word-break: break-word;
}}

.ez-stat-unit {{
    color: {t["ink_faint"]};
    font-size: 0.8rem;
    font-weight: 600;
    margin-left: 0.18rem;
}}

.ez-stat-bar {{
    height: 4px;
    margin-top: 0.55rem;
    overflow: hidden;
    border-radius: 999px;
    background: rgba(31, 36, 33, 0.12);
}}

.ez-stat-bar-fill {{
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, {t["jade"]}, rgba(47, 111, 94, 0.45));
}}

.ez-stat-bar-fill.warning {{
    background: linear-gradient(90deg, {t["seal"]}, rgba(163, 58, 43, 0.45));
}}

.ez-subq, .ez-source, .ez-citation {{
    background: rgba(255, 250, 240, 0.58);
    border: 1px solid {t["line_soft"]};
    border-radius: 8px;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35);
}}

.ez-subq {{
    display: flex;
    align-items: flex-start;
    gap: 0.72rem;
    padding: 0.72rem 0.82rem;
    margin-bottom: 0.55rem;
}}

.ez-subq-num {{
    flex: 0 0 auto;
    width: 1.75rem;
    height: 1.75rem;
    display: grid;
    place-items: center;
    border-radius: 50%;
    color: {t["white"]};
    background: {t["seal"]};
    font-size: 0.76rem;
    font-weight: 800;
}}

.ez-subq-text {{
    color: {t["ink"]};
    font-size: 0.92rem;
    line-height: 1.68;
    overflow-wrap: anywhere;
}}

.ez-source {{
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 0.6rem;
    padding: 0.68rem 0.75rem;
    margin-bottom: 0.5rem;
}}

.ez-source-status {{
    width: 1.45rem;
    height: 1.45rem;
    display: grid;
    place-items: center;
    border-radius: 50%;
    color: {t["jade"]};
    background: rgba(47, 111, 94, 0.11);
    font-size: 0.72rem;
    font-weight: 800;
}}

.ez-source-content {{
    min-width: 0;
}}

.ez-source-title {{
    color: {t["ink"]};
    font-size: 0.88rem;
    font-weight: 800;
    line-height: 1.45;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}}

.ez-source-url {{
    color: {t["ink_faint"]};
    font-size: 0.72rem;
    line-height: 1.5;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

.ez-event-log {{
    max-height: 340px;
    overflow-y: auto;
    padding-right: 0.25rem;
}}

.ez-event {{
    display: grid;
    grid-template-columns: 4.8rem 6.2rem minmax(0, 1fr);
    gap: 0.55rem;
    align-items: baseline;
    padding: 0.45rem 0.25rem;
    border-bottom: 1px dashed {t["line_soft"]};
    color: {t["ink_soft"]};
    font-size: 0.78rem;
}}

.ez-event-time {{
    color: {t["ink_faint"]};
}}

.ez-event-type {{
    color: {t["seal"]};
    font-weight: 800;
    text-transform: uppercase;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.ez-event-msg {{
    min-width: 0;
    overflow-wrap: anywhere;
    line-height: 1.6;
}}

.ez-report {{
    background:
        linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(248, 241, 225, 0.95)),
        {t["paper"]};
    border: 1px solid {t["line"]};
    border-radius: 8px;
    padding: clamp(1.2rem, 3vw, 2.15rem);
    color: {t["ink"]};
    line-height: 1.86;
    box-shadow: 0 16px 36px rgba(61, 45, 24, 0.08);
}}

.ez-report h1, .ez-report h2, .ez-report h3, .ez-report h4 {{
    color: {t["ink"]};
    font-weight: 800;
    letter-spacing: 0 !important;
}}

.ez-report h1 {{
    font-size: clamp(1.5rem, 4vw, 2rem);
    padding-bottom: 0.55rem;
    border-bottom: 2px solid rgba(163, 58, 43, 0.28);
}}

.ez-report h2 {{
    color: {t["jade"]};
    font-size: 1.34rem;
    margin-top: 1.5em;
}}

.ez-report h3 {{
    font-size: 1.08rem;
}}

.ez-report a {{
    color: {t["seal"]};
    text-decoration: none;
    border-bottom: 1px dotted rgba(163, 58, 43, 0.65);
}}

.ez-report code {{
    color: {t["seal"]};
    background: rgba(163, 58, 43, 0.09);
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
}}

.ez-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.36rem;
    border-radius: 999px;
    padding: 0.22rem 0.58rem;
    font-size: 0.74rem;
    font-weight: 800;
    border: 1px solid transparent;
    white-space: nowrap;
}}

.ez-badge-dot {{
    width: 0.42rem;
    height: 0.42rem;
    border-radius: 50%;
}}

.ez-badge.created {{
    color: {t["gold"]};
    background: rgba(155, 113, 61, 0.10);
    border-color: rgba(155, 113, 61, 0.24);
}}
.ez-badge.created .ez-badge-dot {{ background: {t["gold"]}; }}

.ez-badge.running {{
    color: {t["jade"]};
    background: rgba(47, 111, 94, 0.10);
    border-color: rgba(47, 111, 94, 0.24);
}}
.ez-badge.running .ez-badge-dot {{ background: {t["jade"]}; }}

.ez-badge.done {{
    color: {t["jade"]};
    background: rgba(47, 111, 94, 0.12);
    border-color: rgba(47, 111, 94, 0.24);
}}
.ez-badge.done .ez-badge-dot {{ background: {t["jade"]}; }}

.ez-badge.failed {{
    color: {t["seal"]};
    background: rgba(163, 58, 43, 0.11);
    border-color: rgba(163, 58, 43, 0.25);
}}
.ez-badge.failed .ez-badge-dot {{ background: {t["seal"]}; }}

.ez-badge.timeout {{
    color: {t["gold"]};
    background: rgba(155, 113, 61, 0.12);
    border-color: rgba(155, 113, 61, 0.25);
}}
.ez-badge.timeout .ez-badge-dot {{ background: {t["gold"]}; }}

.ez-history-item {{
    background: rgba(255, 250, 240, 0.58);
    border: 1px solid {t["line_soft"]};
    border-radius: 8px;
    padding: 0.7rem 0.78rem;
    margin-bottom: 0.55rem;
}}

.ez-history-item.active {{
    border-color: rgba(163, 58, 43, 0.45);
    box-shadow: inset 3px 0 0 {t["seal"]};
}}

.ez-history-query {{
    color: {t["ink"]};
    font-size: 0.86rem;
    font-weight: 800;
    line-height: 1.48;
    margin-bottom: 0.5rem;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}}

.ez-history-meta {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    color: {t["ink_faint"]};
    font-size: 0.72rem;
}}

.ez-citation {{
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 0.72rem;
    padding: 0.8rem;
    margin-bottom: 0.55rem;
}}

.ez-citation.unused {{
    opacity: 0.58;
}}

.ez-citation-id {{
    color: {t["white"]};
    background: {t["seal"]};
    border-radius: 5px;
    padding: 0.14rem 0.45rem;
    font-weight: 800;
    height: fit-content;
}}

.ez-citation-title {{
    color: {t["ink"]};
    font-size: 0.9rem;
    font-weight: 800;
    line-height: 1.48;
}}

.ez-citation-snippet {{
    color: {t["ink_soft"]};
    font-size: 0.8rem;
    line-height: 1.6;
    margin: 0.25rem 0;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}}

.ez-citation-link {{
    color: {t["jade"]};
    font-size: 0.72rem;
    text-decoration: none;
    overflow-wrap: anywhere;
}}

.ez-empty {{
    color: {t["ink_faint"]};
    padding: 1rem 0.4rem;
    text-align: center;
    font-size: 0.88rem;
}}

.ez-topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    background:
        linear-gradient(180deg, rgba(255, 250, 240, 0.86), rgba(247, 241, 229, 0.92)),
        {t["paper"]};
    border: 1px solid {t["line"]};
    border-radius: 8px;
    box-shadow: 0 12px 28px rgba(61, 45, 24, 0.07);
    padding: 0.95rem 1.1rem;
    margin-bottom: 1rem;
}}

.ez-topbar-left {{
    min-width: 0;
}}

.ez-topbar-query {{
    color: {t["ink"]};
    font-size: 1rem;
    font-weight: 800;
    line-height: 1.48;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
}}

.ez-topbar-meta {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.45rem;
    color: {t["ink_faint"]};
    font-size: 0.72rem;
    margin-top: 0.25rem;
}}

.stTextArea textarea, .stTextInput input {{
    color: {t["ink"]} !important;
    background: rgba(255, 250, 240, 0.80) !important;
    border: 1px solid {t["line"]} !important;
    border-radius: 8px !important;
    box-shadow: inset 0 2px 8px rgba(61, 45, 24, 0.05) !important;
}}

.stTextArea textarea:focus, .stTextInput input:focus {{
    border-color: rgba(47, 111, 94, 0.58) !important;
    box-shadow: 0 0 0 3px rgba(47, 111, 94, 0.12) !important;
}}

div[data-baseweb="select"] > div {{
    color: {t["ink"]} !important;
    background: rgba(255, 250, 240, 0.80) !important;
    border-color: {t["line"]} !important;
    border-radius: 8px !important;
}}

.stSlider [data-baseweb="slider"] > div > div > div {{
    background: {t["jade"]} !important;
}}

.stButton > button {{
    min-height: 2.55rem !important;
    border-radius: 8px !important;
    border: 1px solid rgba(31, 36, 33, 0.16) !important;
    background:
        linear-gradient(180deg, rgba(255,255,255,0.20), transparent),
        {t["ink"]} !important;
    color: {t["white"]} !important;
    box-shadow: 0 8px 20px rgba(31, 36, 33, 0.14) !important;
    font-weight: 800 !important;
    white-space: normal !important;
    line-height: 1.25 !important;
}}

.stButton > button:hover {{
    border-color: rgba(163, 58, 43, 0.42) !important;
    background:
        linear-gradient(180deg, rgba(255,255,255,0.14), transparent),
        {t["seal"]} !important;
    color: {t["white"]} !important;
}}

.stButton > button[kind="secondary"] {{
    color: {t["ink"]} !important;
    background: rgba(255, 250, 240, 0.76) !important;
    border-color: {t["line"]} !important;
    box-shadow: none !important;
}}

.stButton > button[kind="secondary"]:hover {{
    color: {t["seal"]} !important;
    border-color: rgba(163, 58, 43, 0.36) !important;
}}

[data-testid="stExpander"] {{
    border: 1px solid {t["line_soft"]} !important;
    border-radius: 8px !important;
    background: rgba(255, 250, 240, 0.36) !important;
}}

[data-testid="stExpander"] details summary {{
    color: {t["ink"]} !important;
    font-weight: 800 !important;
}}

hr {{
    border-color: {t["line_soft"]} !important;
}}

::-webkit-scrollbar {{
    width: 8px;
    height: 8px;
}}

::-webkit-scrollbar-track {{
    background: rgba(31, 36, 33, 0.05);
}}

::-webkit-scrollbar-thumb {{
    background: rgba(31, 36, 33, 0.26);
    border-radius: 999px;
}}

@media (max-width: 900px) {{
    .block-container {{
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
    }}

    .ez-pipeline {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}

    .ez-pipeline::before {{
        display: none;
    }}

    .ez-stat-grid {{
        grid-template-columns: 1fr;
    }}

    .ez-event {{
        grid-template-columns: 1fr;
        gap: 0.14rem;
    }}

    .ez-topbar {{
        align-items: flex-start;
        flex-direction: column;
    }}
}}
</style>
"""
