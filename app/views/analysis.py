import pandas as pd
import streamlit as st

import data
import ui
from views._ctx import ctx, need_client

METRICS = ["revenue", "cost_of_goods_sold", "gross_profit", "operating_expenses", "operating_income", "net_income"]
LABEL = {k: k.replace("_", " ").title() for k in METRICS}


def _grid(rows: dict, months: list[str], fmt=ui.money) -> None:
    ui.table([{"Item": name, **{mo: fmt(vals.get(mo)) for mo in months}} for name, vals in rows.items()])


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Financial Analysis", f"{client} · period {period or 'n/a'}")
    p = data.load_packet(client, period)
    if not p.ok:
        return ui.empty_state("review packet", p.path, p.error)
    ui.locked_banner(data.load_approval(client, period).data)
    months_data = p.data.get("months", {})
    months = list(months_data)

    xl = data.reviewer_excel(client, period)
    if xl:
        st.download_button("Download reviewer Excel", xl[1], file_name=xl[0],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.caption(f"Reviewer Excel not available yet: outputs/{client}/monthly_review_{period}.xlsx")

    tabs = st.tabs(["Revenue by stream", "Margins", "Opex by category", "MoM", "TTM"])
    tb = data.load_tables(client, period)

    with tabs[0]:
        if tb.ok:
            _grid(tb.data["revenue_by_stream"], tb.data["months"])
            ui.source_note(tb.path)
        else:
            ui.empty_state("revenue by stream", tb.path, tb.error)

    with tabs[1]:
        rows = []
        for mo in months:
            v = months_data[mo]
            rows.append({"Month": mo,
                         "Gross margin": ui.pct(v.get("gross_profit", {}).get("margin")),
                         "Operating margin": ui.pct(v.get("operating_income", {}).get("margin")),
                         "Net margin": ui.pct(v.get("net_income", {}).get("margin")),
                         "Gross margin change": ui.pp(v.get("gross_profit", {}).get("margin_change_pp")) or "n/a"})
        ui.table(rows)
        st.line_chart(pd.DataFrame({"Gross margin": {mo: months_data[mo].get("gross_profit", {}).get("margin") for mo in months}}),
                      color=ui.NAVY, height=220)
        ui.source_note(p.path)

    with tabs[2]:
        if tb.ok:
            _grid(tb.data["opex_by_category"], tb.data["months"])
            ui.source_note(tb.path)
        else:
            ui.empty_state("opex by category", tb.path, tb.error)

    with tabs[3]:
        rows = []
        for mo in months:
            row = {"Month": mo}
            for k in METRICS:
                v = months_data[mo].get(k, {})
                row[LABEL[k] + " $Δ"] = ui.delta(v.get("mom_change")) or "n/a"
                row[LABEL[k] + " %Δ"] = ui.pct(v.get("mom_pct"))
            rows.append(row)
        ui.table(rows)
        ui.source_note(p.path)

    with tabs[4]:
        have = [mo for mo in months if months_data[mo].get("revenue", {}).get("ttm") is not None]
        if not have:
            st.info("TTM is not available: twelve consecutive months are required.")
        rows = []
        for mo in months:
            row = {"Month": mo}
            for k in METRICS:
                t = months_data[mo].get(k, {}).get("ttm")
                row[LABEL[k]] = ui.money(t) if t is not None else "not available"
            rows.append(row)
        ui.table(rows)
        ui.source_note(p.path)
