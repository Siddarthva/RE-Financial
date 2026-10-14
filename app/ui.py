"""Presentation helpers only: styling and number *formatting* (no arithmetic, no file access)."""
from __future__ import annotations

import math
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


def empty_state(what: str, path: str, detail: str = "") -> None:
    extra = f"<br>{detail}" if detail else ""
    st.markdown(
        f'<div class="crw-empty"><strong>No data: {what}</strong><br>'
        f"Expected <code>{path}</code>.{extra}<br>"
        "Run the engine for this client and period, then reload.</div>",
        unsafe_allow_html=True,
    )


def source_note(path: str) -> None:
    st.markdown(f'<div class="crw-cap">Source: <code>{path}</code></div>', unsafe_allow_html=True)


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
