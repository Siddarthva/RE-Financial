import pandas as pd
import streamlit as st

import ui
from views._ctx import need_run


def _strip(run, intake, manifest):
    st.markdown("**Source**")
    m = manifest.data if manifest.ok else {}
    sha = (m.get("source") or {}).get("sha256") or (intake.data or {}).get("sha256")
    cols = st.columns(5)
    cols[0].caption("Workbook hash")
    cols[0].code((sha or "n/a")[:16], language=None)
    cols[1].caption("Period")
    cols[1].write(run.month or "n/a")
    cols[2].caption("Run ID")
    cols[2].write(m.get("run_id", "n/a"))
    cols[3].caption("Skill version")
    cols[3].write(m.get("skill_version") or "n/a")
    cols[4].caption("Intake status")
    cols[4].write(str((intake.data or {}).get("status", "n/a")).title() if intake.ok else "n/a")
    for got in (intake, manifest):
        ui.source_note(got.path) if got.ok else ui.missing(got)


def _figures(run, p):
    m = p.data["months"].get(run.month, {})
    gp, oi = m.get("gross_profit", {}), m.get("operating_income", {})
    cash = p.data.get("cash") or {}
    win = cash.get("primary_window")
    rw = cash.get("runway_months", {})

    c = st.columns(4)
    c[0].metric("Revenue", ui.money(m.get("revenue", {}).get("value")),
                ui.delta(m.get("revenue", {}).get("mom_change"), m.get("revenue", {}).get("mom_pct")))
    c[1].metric("Gross margin", ui.pct(gp.get("margin")), ui.pp(gp.get("margin_change_pp")))
    c[2].metric("Operating expenses", ui.money(m.get("operating_expenses", {}).get("value")),
                ui.delta(m.get("operating_expenses", {}).get("mom_change"), m.get("operating_expenses", {}).get("mom_pct")),
                delta_color="inverse")
    c[3].metric("Operating income", ui.money(oi.get("value")), ui.delta(oi.get("mom_change"), oi.get("mom_pct")))
    c = st.columns(3)
    ni = m.get("net_income", {})
    c[0].metric("Net income", ui.money(ni.get("value")), ui.delta(ni.get("mom_change"), ni.get("mom_pct")))
    c[1].metric("Cash", ui.money(cash.get("value")) if cash else "n/a",
                ui.delta(cash.get("mom_change"), cash.get("mom_pct")) if cash else None)
    c[2].metric(f"Runway ({win} burn)" if win else "Runway", f"{rw[win]:.1f} months" if win in rw else "n/a")
    ui.source_note(p.path)

    st.subheader("Revenue and net income, all months")
    chart = pd.DataFrame({
        "Revenue": {k: v.get("revenue", {}).get("value") for k, v in p.data["months"].items()},
        "Net income": {k: v.get("net_income", {}).get("value") for k, v in p.data["months"].items()},
    })
    st.line_chart(chart, color=[ui.NAVY, ui.ACCENT], height=280)
    ui.source_note(p.path)
    for w in p.data.get("warnings") or []:
        st.warning(w)


def _commentary(run):
    st.subheader("Commentary")
    cm, fg = run.text("commentary"), run.final_grade()
    if not cm.ok:
        return ui.missing(cm)
    if fg:
        st.markdown(f"**Final code grade:** {'Passed' if fg.get('passed') else 'Failed'} - numbers matched {fg.get('numbers')}.")
    else:
        st.caption("No final grade recorded in this run (run.json, " + run.filename("final_grade") + ").")
    st.caption("Statement text is written by Claude and graded by code. Shown verbatim.")
    st.markdown(ui.scrub(cm.data).replace("$", "\\$"))  # $ would start LaTeX
    ui.source_note(cm.path)


def render():
    run = need_run("Overview")
    if not run:
        return
    ap = run.json("approval")
    ui.locked_banner(ap.data if ap.ok else None)
    p = run.json("packet")
    if p.ok:
        _figures(run, p)
    else:
        ui.missing(p)
    _commentary(run)
    _strip(run, run.json("intake"), run.manifest())
