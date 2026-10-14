import streamlit as st

import actions
import data
import ui
from views._ctx import ctx, need_client

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
REASON_LABEL = {"SIGN_FLIP": "Sign flip", "LARGE_MOVE": "Large move"}


def _flux(client, period):
    f = data.load_flux(client, period)
    if not f.ok:
        return ui.empty_state("flux table", f.path, f.error)
    items = sorted(f.data.get("items", []), key=lambda i: abs(i.get("dollar_change") or 0), reverse=True)
    st.subheader("Flagged items")
    st.caption(f"{period} vs {f.data.get('prior_period')}, sorted by size of $ change. Severity comes from the reason code.")
    if not items:
        st.caption("Nothing flagged under the current threshold rule.")
        return ui.source_note(f.path)
    rows = [{"Severity": (i.get("severity") or "n/a").title(),
             "Reason": REASON_LABEL.get(i.get("reason_code"), i.get("reason_code")),
             "Account": i.get("account"), "Section": i.get("section"),
             "Current": ui.money2(i.get("current")), "Prior": ui.money2(i.get("prior")),
             "$ change": ui.money2(i.get("dollar_change")), "% change": ui.pct(i.get("pct_change"))} for i in items]
    sel = st.dataframe(rows, width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="flux_sel")
    picked = sel.selection.rows if sel and sel.selection else []
    if picked:
        i = items[picked[0]]
        st.markdown("#### Evidence")
        ui.table([
            {"Field": "Metric", "Value": i.get("metric")},
            {"Field": "Current", "Value": ui.money2(i.get("current"))},
            {"Field": "Prior", "Value": ui.money2(i.get("prior"))},
            {"Field": "$ change", "Value": ui.money2(i.get("dollar_change"))},
            {"Field": "% change", "Value": ui.pct(i.get("pct_change"))},
            {"Field": "Source cell (current)", "Value": i.get("source_cell_current")},
            {"Field": "Source cell (prior)", "Value": i.get("source_cell_prior")},
            {"Field": "Threshold rule", "Value": i.get("threshold_rule")},
        ])
    else:
        st.caption("Select a row to see its evidence.")
    ui.source_note(f.path)


def _reviewer(client, period):
    r = data.load_review(client, period)
    if not r.ok:
        return ui.empty_state("finance-reviewer output", r.path, r.error), None
    st.subheader("Reviewer questions")
    qs = r.data.get("open_questions") or []
    if qs:
        for n, q in enumerate(qs, 1):
            st.markdown(f"{n}. {q.get('question', '')}")
    else:
        st.caption("None.")
    st.subheader("Finance-reviewer notes")
    st.markdown(f"**Verdict:** {str(r.data.get('verdict', 'n/a')).title()}")
    changes = r.data.get("changes") or []
    if changes:
        st.markdown("**Requested changes**")
        ui.table(changes)
    ui.table([{"Statement": n.get("statement"), "Status": n.get("status"), "Note": n.get("note") or ""}
              for n in r.data.get("statement_notes", [])])
    ui.source_note(r.path)
    return None, r.data.get("verdict")


def _approval(client, period, verdict):
    st.subheader("Approval")
    ap = data.load_approval(client, period)
    rec = ap.data if ap.ok else None
    locked = bool(rec and rec.get("status") == "approved")
    if rec:
        ui.table([{"Status": rec.get("status", "").title() + (" (locked)" if locked else ""),
                   "Reviewer": rec.get("reviewer"), "Reason": rec.get("reason"), "Decided at": rec.get("decided_at")}])
    else:
        st.caption("No decision recorded for this period.")
    if not locked:
        if verdict != "approve":
            st.caption(f"Approve is blocked by the engine unless the finance-reviewer verdict is 'approve' (currently {verdict or 'n/a'}).")
        with st.form("decision"):
            name = st.text_input("Reviewer name")
            reason = st.text_area("Reason")
            c = st.columns(2)
            approve = c[0].form_submit_button("Approve", type="primary")
            reject = c[1].form_submit_button("Reject")
        if approve or reject:
            if not name.strip() or not reason.strip():
                st.error("Reviewer name and reason are both required.")
            else:
                ok, msg = actions.decide(client, period, name.strip(), reason.strip(), reject=reject)
                (st.success if ok else st.error)(msg or ("Recorded." if ok else "The decision was not recorded."))
                if ok:
                    st.rerun()
    st.markdown("**Audit log entries for this period**")
    a = data.load_audit_log(client)
    if a.ok:
        rows = [e for e in a.data if e.get("period") == period]
        ui.table(rows) if rows else st.caption("No entries yet.")
        ui.source_note(a.path)
    else:
        ui.empty_state("audit log", a.path, a.error)


def render():
    client = need_client()
    if not client:
        return
    _, period = ctx()
    ui.title("Insights & Review", f"{client} · period {period or 'n/a'}")
    if not period:
        return ui.empty_state("review packet", f"outputs/{client}/review_packet_<period>.json")
    ap = data.load_approval(client, period)
    ui.locked_banner(ap.data if ap.ok else None)
    _flux(client, period)
    _, verdict = _reviewer(client, period)
    _approval(client, period, verdict)
