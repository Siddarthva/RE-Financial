import streamlit as st

import data
import ui
from views._ctx import need_client


def render():
    client = need_client()
    if not client:
        return
    ui.title("Evaluations", client)
    e = data.load_eval_results(client)
    if not e.ok:
        return ui.empty_state("eval results", e.path, e.error)
    for item in e.data:
        c = item["content"]
        st.subheader(item["file"])
        if isinstance(c, dict) and "numbers_checked" in c:
            k = st.columns(3)
            k[0].metric("Result", "Passed" if c.get("passed") else "Failed")
            k[1].metric("Numbers checked", c.get("numbers_checked"))
            k[2].metric("Numbers matched", c.get("numbers_matched"))
            ui.table([{"Token": n.get("token"), "Kind": n.get("kind"), "Fact": n.get("fact"),
                       "Matched": n.get("matched")} for n in c.get("numbers", [])])
            if c.get("top_movements"):
                ui.table([{"Account": t.get("account"), "Mentioned": t.get("mentioned")}
                          for t in c["top_movements"]])
            if c.get("cash_risk"):
                st.json(c["cash_risk"])
        else:
            st.json(c)
