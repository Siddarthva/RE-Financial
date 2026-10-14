import streamlit as st

import actions
import data
import ui
from views._ctx import ctx, need_client


def _workbook(client, period):
    st.subheader("Workbook")
    i = data.load_intake(client, period)
    if not i.ok:
        return ui.empty_state("intake result", i.path, i.error)
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


def _quickbooks(client):
    st.subheader("QuickBooks")
    s = data.load_qbo_status(client)
    if not s.ok:
        ui.empty_state("QuickBooks status", s.path, s.error)
    else:
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
            (st.success if t.get("ok") else st.error)(f"Last test {t.get('tested_at')}: {t.get('message')}")
        ui.source_note(s.path)
    if st.button("Test connection"):
        with st.spinner("Running read-only CompanyInfo query..."):
            ok, out = actions.test_qbo(client)
        if not ok:
            st.error("The test script could not run. Check that Python and Node.js are installed.")
        st.rerun()


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Data Sources", f"{client} · period {period or 'n/a'}")
    _workbook(client, period)
    _quickbooks(client)
