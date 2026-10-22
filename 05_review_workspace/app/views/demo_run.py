"""One page per demo run folder. Reads files only: nothing here calculates a figure or imports the engine."""
import json
import re

import pandas as pd
import streamlit as st

import data
import ui

STATEMENT = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
FAIL_BANNER = "Code grader failed: not ready for sign-off"
EMPTY_HELP = ("No demo runs yet. In Claude Code run `/demo-run abc 2026-06`; each run creates its own folder "
              "`demo_runs/output_NNN/` and appears here as its own page after a refresh.")


def label(run_dir) -> str:
    """'Output 001 — abc 2026-06 — 2026-10-22 11:18 IST' (text only, from run.json)."""
    n = run_dir.name.removeprefix("output_")
    run = data.load_demo_run(run_dir)
    r = run["run"].data if run["run"].ok else {}
    stamp = ((r.get("started") or {}).get("ist") or "")[:16].replace("T", " ")
    parts = [f"Output {n}"]
    if run["client"] and run["month"]:
        parts.append(f"{run['client']} {run['month']}")
    if stamp:
        parts.append(f"{stamp} IST")
    return " — ".join(parts)


def render_empty():
    ui.title("Demo runs")
    st.markdown(f'<div class="crw-empty"><strong>No demo runs</strong><br>{EMPTY_HELP.replace(chr(96), "")}</div>',
                unsafe_allow_html=True)
    st.code("/demo-run abc 2026-06", language=None)


def _yn(v):
    return "n/a" if v is None else "yes" if v else "no"


def _verdict(v):
    return v if v else "not recorded"


def _json(obj):
    """st.json with credential-looking strings withheld, like every other page."""
    st.json(json.loads(ui.scrub(json.dumps(obj))))


def _grade_state(run):
    """(passed|None, numbers, mismatches) for the final grade: run.json first, then the grade file."""
    r = run["run"].data if run["run"].ok else {}
    fg = r.get("final_grade") or (run["final_grade"].data if run["final_grade"].ok else None)
    if not fg:
        return None, None, []
    return fg.get("passed"), fg.get("numbers"), fg.get("mismatches") or []


def _summary(run, r, passed):
    st.header("1. Run summary")
    c = st.columns(4)
    c[0].metric("Run", f"Output {run['dir'].name.removeprefix('output_')}")
    c[1].metric("Client · month", f"{run['client'] or 'n/a'} · {run['month'] or 'n/a'}")
    c[2].metric("Started (IST)", ((r.get("started") or {}).get("ist") or "n/a")[:19].replace("T", " "))
    c[3].metric("Final code grade", "PASS" if passed else "FAIL" if passed is not None else "not recorded")
    c = st.columns(4)
    c[0].metric("Branch", r.get("git_branch") or "n/a")
    c[1].metric("Commit", (r.get("git_head") or "n/a")[:10])
    c[2].metric("Workbook SHA-256 (first 16)", r.get("workbook_sha256_16") or "n/a")
    c[3].metric("Reviewer verdict (first → final)",
                f"{_verdict(r.get('reviewer_first_verdict'))} → {_verdict(r.get('reviewer_final_verdict'))}")
    c = st.columns(4)
    c[0].metric("Grade retry used", _yn(r.get("retry_used")))
    c[1].metric("Open questions", "n/a" if r.get("open_question_count") is None else r["open_question_count"])
    st.markdown("**Stage statuses**")
    stages = r.get("stages") or {}
    if stages:
        ui.table([{"Stage": k, "Status": v} for k, v in stages.items()])
    else:
        st.caption("No stage statuses recorded in run.json.")


def _headline(run):
    st.header("2. Headline numbers")
    p = run["packet"]
    if not p.ok:
        return st.caption(f"Not available: {run['files']['packet']}")
    m = p.data.get("months", {}).get(run["month"], {})
    gp, oi = m.get("gross_profit", {}), m.get("operating_income", {})
    cash = p.data.get("cash") or {}
    win = cash.get("primary_window")
    rw = cash.get("runway_months") or {}
    rev, opex, ni = m.get("revenue", {}), m.get("operating_expenses", {}), m.get("net_income", {})
    c = st.columns(3)
    c[0].metric("Revenue", ui.money(rev.get("value")), ui.delta(rev.get("mom_change"), rev.get("mom_pct")))
    c[1].metric("Gross margin", ui.pct(gp.get("margin")), ui.pp(gp.get("margin_change_pp")))
    c[2].metric("OPEX", ui.money(opex.get("value")), ui.delta(opex.get("mom_change"), opex.get("mom_pct")), delta_color="inverse")
    c = st.columns(3)
    c[0].metric("Net income", ui.money(ni.get("value")), ui.delta(ni.get("mom_change"), ni.get("mom_pct")))
    c[1].metric("Cash", ui.money(cash.get("value")) if cash else "n/a",
                ui.delta(cash.get("mom_change"), cash.get("mom_pct")) if cash else None)
    c[2].metric(f"Runway ({win} burn)" if win else "Runway", f"{rw[win]:.1f} months" if win in rw else "n/a")
    ui.source_note(p.path)


def _notes(review):
    """{statement number: (status, note)} from a reviewer JSON; falls back to its `changes` list."""
    out = {}
    if not review.ok:
        return out
    for n in review.data.get("statement_notes") or []:
        out[n.get("statement")] = (n.get("status"), n.get("note") or "")
    for ch in review.data.get("changes") or []:
        out[ch.get("statement")] = ("change", ch.get("issue") or "")
    return out


def _commentary_table(run, r):
    st.header("3. Commentary review")
    cm = run["commentary"]
    if not cm.ok:
        return st.caption(f"Not available: {run['files']['commentary']}")
    st.caption("Statement text is written by Claude, graded by code. Shown verbatim from the commentary file.")
    first, final = _notes(run["review_first"]), _notes(run["review"])
    rows = []
    for line in cm.data.splitlines():
        m = STATEMENT.match(line)
        if m:
            n = int(m.group(1))
            f1, f2 = first.get(n), final.get(n)
            rows.append({"#": n, "Statement": m.group(2),
                         "First review": f1[0] if f1 else "-", "Final review": f2[0] if f2 else "-",
                         "Reviewer note": (f2 or f1 or ("", ""))[1], "Flag": "changed in first review" if f1 and f1[0] == "change" else ""})
    c = st.columns(2)
    c[0].metric("First reviewer verdict", _verdict(r.get("reviewer_first_verdict")))
    c[1].metric("Final reviewer verdict", _verdict(r.get("reviewer_final_verdict")))
    if not rows:
        return st.caption("No numbered statements found in the commentary file.")
    df = pd.DataFrame(rows)
    st.dataframe(df.style.apply(lambda row: ["background-color: #FBE3D6" if row["Flag"] else "" for _ in row], axis=1),
                 width="stretch", hide_index=True)
    if not run["review"].ok:
        st.caption(f"Reviewer columns empty: {run['files']['review']} is missing.")


def _grade_history(run, r, passed, numbers, mismatches):
    st.header("4. Grade history")
    attempts = r.get("grade_attempts") or (run["grade_record"].data.get("attempts") if run["grade_record"].ok else None)
    if attempts:
        ui.table([{"Attempt": i, "Result": "PASS" if a.get("passed") else "FAIL", "Numbers matched": a.get("numbers"),
                   "Mismatches": len(a.get("mismatches") or []), "Detail": "; ".join(a.get("mismatches") or [])}
                  for i, a in enumerate(attempts, 1)])
    else:
        st.caption("No grade attempts recorded.")
    if passed is None:
        st.warning("No final grade recorded for this run.")
    else:
        st.markdown(f"**Final grade: {'PASS' if passed else 'FAIL'}** — numbers matched {numbers}; mismatches {len(mismatches)}")
        for m_ in mismatches:
            st.write(f"- {m_}")


def _scores(run):
    st.header("5. Reviewer scores and open questions")
    rv = run["review"]
    if not rv.ok:
        return st.caption(f"Not available: {run['files']['review']}")
    scores = rv.data.get("scores") or {}
    c = st.columns(4)
    for col, key in zip(c, ("numbers", "coverage", "causes", "tone")):
        s = scores.get(key) or {}
        col.metric(key.title(), f"{s['ok']} / {s['of']}" if "ok" in s and "of" in s else "n/a")
    qs = rv.data.get("open_questions") or []
    st.markdown(f"**Open questions ({len(qs)})**")
    if not qs:
        st.caption("None.")
    for q in qs:
        st.markdown(f"- {q.get('question', '')}" + (f"  \n  *Why:* {q['why']}" if q.get("why") else ""))


def _movements(run):
    st.header("6. Top movements and flux items")
    p, fx = run["packet"], run["flux"]
    if p.ok:
        mv = p.data.get("top_movements") or []
        st.markdown("**Top movements (month over month)**")
        ui.table([{"Account": x.get("account"), "Change": ui.money2(x.get("mom_change"))} for x in mv]) if mv else st.caption("None.")
    else:
        st.caption(f"Top movements not available: {run['files']['packet']}")
    if fx.ok:
        items = fx.data.get("items") or []
        st.markdown(f"**Flux items ({len(items)})**")
        ui.table([{"Account": i.get("account"), "Section": i.get("section"), "Reason": i.get("reason_code"),
                   "Severity": i.get("severity"), "Current": ui.money2(i.get("current")), "Prior": ui.money2(i.get("prior")),
                   "Change": ui.money2(i.get("dollar_change")), "Change %": ui.pct(i.get("pct_change")),
                   "Source cell": i.get("source_cell_current")} for i in items]) if items else st.caption("None flagged.")
    else:
        st.caption(f"Flux items not available: {run['files']['flux']}")


def _memo(run):
    st.header("7. Owner memo")
    if run["memo"].ok:
        st.markdown(ui.scrub(run["memo"].data).replace("$", "\\$"))  # $ would start LaTeX
    else:
        st.caption(f"Not available: {run['files']['memo']}")


def _raw(run):
    st.header("8. Raw files")
    items = [("Review packet JSON", run["packet"], "packet"), ("Review JSON (final)", run["review"], "review"),
             ("Review JSON (first)", run["review_first"], "review_first"), ("Grade record JSON (attempts)", run["grade_record"], "grade_record"),
             ("Final grade JSON", run["final_grade"], "final_grade"), ("Flux JSON", run["flux"], "flux"), ("run.json", run["run"], None)]
    for title, loaded, key in items:
        with st.expander(title):
            if loaded.ok:
                _json(loaded.data)
                ui.source_note(loaded.path)
            else:
                st.caption(f"Not available: {run['files'][key] if key else 'run.json'}")


def _download(run):
    st.header("9. Excel pack")
    if run["pack"]:
        name, blob = run["pack"]
        st.download_button(f"Download {name}", data=blob, file_name=name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.caption(f"Not available: {run['files']['pack']}")


def render_body(run_dir):
    """Every section for one run folder (banner, summary, commentary review, grades, raw JSON, pack). Used by the run page and the Runs page."""
    run = data.load_demo_run(run_dir)
    r = run["run"].data if run["run"].ok else {}
    passed, numbers, mismatches = _grade_state(run)
    if passed is False:
        st.error(FAIL_BANNER)
    if run["missing"]:
        st.warning("Missing files in this run: " + ", ".join(run["missing"]))
    _summary(run, r, passed)
    _headline(run)
    _commentary_table(run, r)
    _grade_history(run, r, passed, numbers, mismatches)
    _scores(run)
    _movements(run)
    _memo(run)
    _raw(run)
    _download(run)


def render_run(run_dir):
    ui.title(label(run_dir), "Demo run · read from the run folder only; nothing on this page is calculated")
    render_body(run_dir)
