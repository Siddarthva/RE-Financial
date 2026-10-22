import streamlit as st

import ui
from views._ctx import need_run

REASON_LABEL = {"SIGN_FLIP": "Sign flip", "LARGE_MOVE": "Large move"}


def _flux(run):
    f = run.json("flux")
    if not f.ok:
        return ui.missing(f)
    items = sorted(f.data.get("items", []), key=lambda i: abs(i.get("dollar_change") or 0), reverse=True)
    st.subheader("Flagged items")
    st.caption(f"{run.month} vs {f.data.get('prior_period')}, sorted by size of $ change. Severity comes from the reason code.")
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


def _reviewer(run):
    r = run.json("review")
    if not r.ok:
        return ui.missing(r), None
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


def _approval(run):
    st.subheader("Approval")
    ap = run.json("approval")
    if ap.ok:
        rec = ap.data
        locked = rec.get("status") == "approved"
        ui.table([{"Status": rec.get("status", "").title() + (" (locked)" if locked else ""),
                   "Reviewer": rec.get("reviewer"), "Reason": rec.get("reason"), "Decided at": rec.get("decided_at")}])
        ui.source_note(ap.path)
    else:
        ui.missing(ap)
    st.markdown("**Audit log entries for this run**")
    a = run.json("audit_log")
    if a.ok:
        rows = [e for e in a.data if e.get("period") == run.month]
        ui.table(rows) if rows else st.caption("No entries for this period in the run's audit log.")
        ui.source_note(a.path)
    else:
        ui.missing(a)


def render():
    run = need_run("Insights & Review")
    if not run:
        return
    ap = run.json("approval")
    ui.locked_banner(ap.data if ap.ok else None)
    _flux(run)
    _reviewer(run)
    _approval(run)
