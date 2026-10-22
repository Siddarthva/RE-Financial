import streamlit as st

import ui
from views._ctx import need_run


def _workbook(run):
    st.subheader("Workbook")
    i = run.json("intake")
    if not i.ok:
        return ui.missing(i)
    d = i.data
    ui.table([
        {"Field": "Workbook", "Value": d.get("workbook")},
        {"Field": "Sheets detected", "Value": ", ".join(d.get("sheets_detected", []))},
        {"Field": "Period range", "Value": f"{d.get('period_start')} to {d.get('period_end')} ({d.get('months')} months)"},
        {"Field": "SHA-256", "Value": d.get("sha256")},
        {"Field": "Intake status", "Value": str(d.get("status", "n/a")).title()},
    ])
    st.markdown("**Intake checks**")
    for c in d.get("checks", []):
        mark = "PASS" if c.get("passed") else "FAIL"
        detail = f" - {c['detail']}" if c.get("detail") else ""
        line = f"**{mark}** · {c.get('check')} · `{c.get('cell_ref')}`{detail}"
        (st.markdown if c.get("passed") else st.error)(line)
    ui.source_note(i.path)


def _quickbooks(run):
    st.subheader("QuickBooks")
    s = run.json("qbo_status")
    if not s.ok:
        return ui.missing(s)
    d = s.data
    ui.table([
        {"Field": "Method", "Value": d.get("method")},
        {"Field": "Last successful retrieval", "Value": d.get("last_successful_retrieval") or "none on record"},
        *[{"Field": k, "Value": v} for k, v in (d.get("flags") or {}).items()],
    ])
    if d.get("flags_source"):
        st.caption(f"Flags: {d['flags_source']}")
    t = d.get("last_test")
    if t:
        (st.success if t.get("ok") else st.error)(f"Last test {t.get('tested_at')}: {ui.scrub(t.get('message'))}")
    ui.source_note(s.path)


def render():
    run = need_run("Data Sources")
    if not run:
        return
    _workbook(run)
    _quickbooks(run)
