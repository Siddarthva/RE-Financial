"""Presentation helpers only: styling and number *formatting* (no arithmetic, no file access)."""
from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd
import streamlit as st

NAVY = "#14284B"
ACCENT = "#C8742B"
MUTED = "#5B6577"
LINE = "#D9DEE7"

APP_NAME = "Close Review Workspace"

_CSS = f"""
<style>
html, body, [data-testid="stAppViewContainer"] {{ background: #FFFFFF; color: {NAVY}; }}
[data-testid="stSidebar"] {{ background: {NAVY}; }}
[data-testid="stSidebar"] * {{ color: #FFFFFF !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] * {{ color: {NAVY} !important; }}
h1, h2, h3 {{ color: {NAVY}; font-weight: 600; letter-spacing: -0.01em; }}
h1 {{ border-bottom: 3px solid {ACCENT}; padding-bottom: .35rem; }}
[data-testid="stMetric"] {{ border: 1px solid {LINE}; border-left: 4px solid {NAVY};
  padding: .6rem .9rem; border-radius: 4px; background: #FFFFFF; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }}
[data-testid="stMetricValue"] {{ color: {NAVY}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 4px; }}
.crw-empty {{ border: 1px dashed {MUTED}; border-left: 4px solid {ACCENT}; padding: 1rem 1.2rem;
  border-radius: 4px; background: #F6F8FB; color: {NAVY}; }}
.crw-empty code {{ background: #E9EDF4; color: {NAVY}; }}
.crw-cap {{ color: {MUTED}; font-size: .85rem; }}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def title(text: str, caption: str = "") -> None:
    st.title(text)
    if caption:
        st.markdown(f'<div class="crw-cap">{caption}</div>', unsafe_allow_html=True)


NO_RUNS = "No runs yet. Click 'Run full analysis with Claude' or run /demo-run abc 2026-06"


def no_runs() -> None:
    st.markdown(f'<div class="crw-empty"><strong>{NO_RUNS}</strong></div>', unsafe_allow_html=True)


def run_header(text: str, run) -> None:
    """Page title plus the line that says which run folder every number on the page comes from."""
    st.title(text)
    st.markdown(f'<div class="crw-cap">Showing: Run {run.number} (<code>{run.folder}</code>)'
                f"{f' · {run.client} {run.month}' if run.client and run.month else ''}</div>", unsafe_allow_html=True)


def missing_name(name: str) -> None:
    st.markdown(f'<div class="crw-empty">Not produced in this run: <code>{name}</code></div>', unsafe_allow_html=True)


def missing(loaded) -> None:
    """A file the run does not contain. Never filled from anywhere else."""
    if loaded.missing:
        missing_name(loaded.name)
    else:
        st.markdown(f'<div class="crw-empty">Could not read <code>{loaded.name}</code>: {scrub(loaded.error)}</div>', unsafe_allow_html=True)


def source_note(path: str) -> None:
    st.markdown(f'<div class="crw-cap">from <code>{path}</code></div>', unsafe_allow_html=True)


def project_banner(sources: list[tuple[str, str]]) -> None:
    """Evaluations and Architecture are project files, not run data: say so, with each source file and its date."""
    files = "; ".join(f"<code>{p}</code> ({d})" for p, d in sources)
    st.markdown(f'<div class="crw-empty"><strong>Project-level results, not from a run</strong><br>Source: {files}</div>',
                unsafe_allow_html=True)


def _missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def money(v: Any) -> str:
    if _missing(v):
        return "n/a"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def money2(v: Any) -> str:
    if _missing(v):
        return "n/a"
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def pct(v: Any) -> str:
    """Engine stores ratios as fractions; this only renders them as a percentage string."""
    return "n/a" if _missing(v) else f"{v * 100:.1f}%"


def table(rows: list[dict] | pd.DataFrame, **kw) -> None:
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True, **kw)


def delta(change: Any, pct_: Any = None) -> str | None:
    """Format an engine-supplied change (and optional % change) as text; no arithmetic."""
    if _missing(change):
        return None
    sign = "+" if change > 0 else "-" if change < 0 else ""
    s = f"{sign}${abs(change):,.0f}"
    if not _missing(pct_):
        s += f" ({'+' if pct_ > 0 else ''}{pct_ * 100:.1f}%)"
    return s


def pp(v: Any) -> str | None:
    """Engine supplies margin change already in percentage points."""
    return None if _missing(v) else f"{'+' if v > 0 else ''}{v:.1f} pp"


def locked_banner(approval) -> None:
    if approval is not None and approval.get("status") == "approved":
        st.markdown(
            f'<div class="crw-empty"><strong>Locked - approved</strong> by {approval.get("reviewer")} '
            f'on {approval.get("decided_at")}. No further changes are accepted for this period.</div>',
            unsafe_allow_html=True)


_SECRET = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"
    r"|(?:AB11|RT1-|AB1|XX11)[A-Za-z0-9_-]{30,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{20,}"
    r"|(?i:realm[_ ]?id)[\"']?\s*[:=]\s*[\"']?\d{6,}|/company/\d{6,}"
    r"|(?i:client[_-]?secret|refresh[_-]?token|access[_-]?token|api[_-]?key|password|authorization[_-]?code)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+=]{8,}"
    r"|[?&]code=[A-Za-z0-9_\-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def scrub(text: str) -> str:
    """Defence in depth: anything that looks like a credential, realm ID or auth code is withheld before display."""
    return _SECRET.sub("[withheld]", text or "")
