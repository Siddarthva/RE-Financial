import streamlit as st

import data
import ui
from views._ctx import need_client


def render():
    client = need_client()
    if not client:
        return
    ui.title("Runs", client)
    st.subheader("Run manifests")
    m = data.load_manifests(client)
    if m.ok:
        for item in m.data:
            with st.expander(item["file"]):
                st.json(item["content"])
    else:
        ui.empty_state("run manifests", m.path, m.error)
    st.subheader("Audit log")
    a = data.load_audit_log(client)
    if a.ok:
        ui.table(a.data)
        ui.source_note(a.path)
    else:
        ui.empty_state("audit log", a.path, a.error)
