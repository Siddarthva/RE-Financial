import pandas as pd
import streamlit as st

import data
import ui
from views._ctx import ctx, need_client


def _strip(client, period, intake, manifest):
    st.markdown("**Source**")
    m = manifest.data if manifest.ok else {}
    src = m.get("source") or {}
    sha = src.get("sha256") or (intake.data or {}).get("sha256")
    cols = st.columns(5)
    cols[0].caption("Workbook hash")
    cols[0].code((sha or "n/a")[:16], language=None)
    cols[1].caption("Period")
    cols[1].write(period)
    cols[2].caption("Run ID")
    cols[2].write(m.get("run_id", "n/a"))
    cols[3].caption("Skill version")
    cols[3].write(m.get("skill_version") or "n/a")
    cols[4].caption("Intake status")
    cols[4].write((intake.data or {}).get("status", "n/a").title() if intake.ok else "n/a")
    if not manifest.ok:
        st.caption(f"No run manifest yet ({manifest.path}).")


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Overview", f"{client} · period {period or 'n/a'}")
    p = data.load_packet(client, period)
    if not p.ok:
        return ui.empty_state("review packet", p.path, p.error)
    ui.locked_banner(data.load_approval(client, period).data)

    m = p.data["months"].get(period, {})
    gp, oi = m.get("gross_profit", {}), m.get("operating_income", {})
    cash = p.data.get("cash") or {}
    win = cash.get("primary_window")
    run = cash.get("runway_months", {})

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
    c[2].metric(f"Runway ({win} burn)" if win else "Runway", f"{run[win]:.1f} months" if win in run else "n/a")

    st.subheader("Revenue and net income, all months")
    chart = pd.DataFrame({
        "Revenue": {k: v.get("revenue", {}).get("value") for k, v in p.data["months"].items()},
        "Net income": {k: v.get("net_income", {}).get("value") for k, v in p.data["months"].items()},
    })
    st.line_chart(chart, color=[ui.NAVY, ui.ACCENT], height=280)

    st.subheader("Commentary")
    cm = data.load_commentary(client, period)
    if cm.ok:
        g = cm.data.get("grade", {})
        st.markdown(f"**Grader:** {'Passed' if g.get('passed') else 'Failed'} - "
                    f"{g.get('numbers_matched')} of {g.get('numbers_checked')} numbers match the engine output.")
        for line in cm.data.get("lines", []):
            st.markdown(line)
        ui.source_note(cm.path)
    else:
        ui.empty_state("graded commentary", cm.path, "Run the pipeline after the commentary draft exists.")

    _strip(client, period, data.load_intake(client, period), data.latest_manifest(client, period))
    warns = p.data.get("warnings") or []
    for w in warns:
        st.warning(w)
