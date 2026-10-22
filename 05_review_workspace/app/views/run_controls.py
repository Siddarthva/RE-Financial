"""The two run buttons. Both create a new runs/runN/ folder; the page then switches to it."""
import re

import streamlit as st

import actions
import data
import ui

HINT = "To run the full analysis with Claude, type /demo-run <client> <YYYY-MM> in Claude Code (the claude CLI was not found on PATH)."
TIMEOUT_MSG = "Claude did not finish within 10 minutes and was stopped. Check runs/ for the run folder (it is kept), or run /demo-run in Claude Code."
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _select(name):
    """Make the sidebar selector pick this run on the next rerun (the selector is already built in this one)."""
    if name:
        st.session_state["run_pick_next"] = name


def _claude(client, period, ok):
    exe = actions.claude_path()
    if not exe:
        return st.caption(HINT)
    if not st.button("Run full analysis with Claude", disabled=not ok,
                     help="Runs: claude -p \"/demo-run <client> <period>\" with the allowed tools of .claude/commands/demo-run.md. "
                          "Takes a few minutes; the run appears as its own Run N."):
        return
    before = {r.name for r in data.list_runs()}
    with st.expander("Live log", expanded=True):
        box = st.empty()
        with st.spinner("Claude is running /demo-run (up to 10 minutes)..."):
            status, log = actions.run_claude(client, period, on_line=lambda t: box.code(ui.scrub(t[-4000:]), language=None))
    new = [r.name for r in data.list_runs() if r.name not in before]
    if new:
        actions.save_claude_log(data.list_runs()[0].dir, status, log)
    _select(new[0] if new else None)
    st.session_state["claude_result"] = {"status": status, "log": ui.scrub(log)[-6000:], "new": new[0] if new else None}
    st.rerun()


def _pipeline(client, period, ok):
    if not st.button("Run pipeline only (no Claude)", type="primary", disabled=not ok,
                     help="Runs scripts/new_run.py for the client and period: a new runs/runN folder with intake, calculate and the evals. "
                          "Its Claude stages are recorded as not run."):
        return
    with st.spinner("Running pipeline..."):
        ok, out = actions.run_analysis(client, period)
    new = actions.new_run_folder(out) if ok else None
    _select(new)
    st.session_state["pipeline_result"] = {"ok": ok, "new": new, "log": ui.scrub(out)}
    st.rerun()


def _results():
    p = st.session_state.pop("pipeline_result", None)
    if p:
        (st.success if p["ok"] else st.error)(f"Pipeline finished. Showing {p['new']}." if p["ok"] else "Pipeline failed.")
        if p["log"] and not p["ok"]:
            st.code(p["log"], language=None)
    res = st.session_state.pop("claude_result", None)
    if res:
        if res["status"] == "ok":
            st.success(f"Claude finished. Showing {res['new']}." if res["new"] else "Claude finished, but no new run folder appeared.")
        elif res["status"] == "timeout":
            st.error(TIMEOUT_MSG)
        else:
            st.error("Claude run failed." if res["status"] == "failed" else "Claude run could not start.")
        if res["log"]:
            with st.expander("Claude log"):
                st.code(res["log"], language=None)


def render(run):
    """Client and period for the NEW run (the selected run's, if there is one); the buttons start a new run folder."""
    _results()
    clients = data.list_clients()
    c = st.columns(2)
    client = c[0].selectbox("Client for a new run", clients, index=clients.index(run.client) if run and run.client in clients else 0) if clients else None
    period = c[1].text_input("Period for a new run (YYYY-MM)", value=run.month if run and run.month else "", placeholder="YYYY-MM").strip()
    if not clients:
        st.caption("No clients found under clients/.")
    ok = bool(client and _PERIOD.match(period))
    _pipeline(client, period, ok)
    _claude(client, period, ok)
