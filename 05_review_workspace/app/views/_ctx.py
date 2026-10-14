import streamlit as st

import ui


def ctx():
    c = st.session_state.get("ctx", {})
    return c.get("client"), c.get("period")


def need_client() -> str | None:
    client, _ = ctx()
    if not client:
        ui.title(ui.APP_NAME)
        ui.empty_state("no client outputs", "outputs/<client>/summary.json")
    return client
