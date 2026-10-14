import streamlit as st

import data
import ui
from views._ctx import ctx, need_client


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Insights & Review", f"{client} · period {period or 'n/a'}")
    r = data.load_review(client, period)
    if r.ok:
        st.metric("Verdict", str(r.data.get("verdict", "n/a")).title())
        st.subheader("Requested changes")
        changes = r.data.get("changes") or []
        if changes:
            ui.table(changes)
        else:
            st.caption("None requested.")
        st.subheader("Statement notes")
        ui.table([{"Statement": n.get("statement"), "Status": n.get("status"), "Note": n.get("note")}
                  for n in r.data.get("statement_notes", [])])
        st.subheader("Open questions")
        for q in r.data.get("open_questions", []):
            with st.expander(q.get("question", "")):
                st.write(q.get("why", ""))
        ui.source_note(r.path)
    else:
        ui.empty_state("reviewer output", r.path, r.error)

    p = data.load_packet(client, period)
    if p.ok:
        st.subheader("Top movements")
        ui.table([{"Account": m.get("account"), "Change": ui.money2(m.get("mom_change"))}
                  for m in p.data.get("top_movements", [])])
        st.subheader("One-offs")
        ui.table([{"Account": o.get("account"), "Section": o.get("section"), "Month": o.get("month"),
                   "Amount": ui.money2(o.get("amount"))} for o in p.data.get("one_offs", [])])
        ui.source_note(p.path)
    else:
        ui.empty_state("review packet", p.path, p.error)
