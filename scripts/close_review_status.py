"""Stage table for /close-review: which of the six close stages has passed, from files on disk. Read-only.

    python scripts/close_review_status.py <client> <YYYY-MM> [--outputs-root DIR]

Stages, in order: 1 Intake, 2 Calculate + flux, 3 Draft, 4 Reviewer, 5 Package, 6 Human approval.
A stage is PASS, FAIL (its gate failed), or NOT RUN (an earlier stage did not pass, or its files are missing).
Stage 6 is WAITING while no human decision exists: the command never approves for anyone.
Exit 0 only when stage 6 is approved; 1 otherwise (the first non-PASS stage is named).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03_evals"))
import grade_commentary as gc  # noqa: E402
import grade_workflow_skills as gw  # noqa: E402

STAGES = ["Intake", "Calculate + flux", "Draft", "Reviewer", "Package", "Human approval"]


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def evaluate(d: Path, month: str) -> list[tuple[str, str, str]]:
    """[(stage, status, note)] for all six stages; stops evaluating after the first non-PASS."""
    rows: list[tuple[str, str, str]] = []

    def done(i, status, note):
        rows.append((STAGES[i], status, note))
        return status == "PASS"

    intake = _json(d / f"intake_{month}.json")
    if intake is None:
        done(0, "NOT RUN", f"intake_{month}.json missing; run scripts/run_pipeline.py")
        return _fill(rows)
    else:
        failed = [c["check"] for c in intake["checks"] if not c["passed"]]
        if not done(0, "PASS" if not failed else "FAIL", f"{len(intake['checks'])} checks" if not failed else f"failed: {'; '.join(failed[:3])}"):
            return _fill(rows)
    packet, flux = _json(d / f"review_packet_{month}.json"), _json(d / f"flux_{month}.json")
    if packet is None or flux is None:
        done(1, "NOT RUN", "review packet or flux file missing")
        return _fill(rows)
    done(1, "PASS", f"{len(flux['items'])} flagged items")
    text_path = d / f"commentary_{month}.md"
    if not text_path.is_file():
        done(2, "NOT RUN", f"commentary_{month}.md missing")
        return _fill(rows)
    g = gc.grade(text_path.read_text(encoding="utf-8"), packet, require_sections=True)
    if not done(2, "PASS" if g["passed"] else "FAIL", f"{g['numbers_matched']}/{g['numbers_checked']} numbers matched" + ("" if g["sections"]["passed"] else "; sections missing: " + ", ".join(g["sections"]["missing"] or ["order"]))):
        return _fill(rows)
    review = _json(d / f"review_{month}.json")
    if review is None:
        done(3, "NOT RUN", f"review_{month}.json missing")
        return _fill(rows)
    if not done(3, "PASS" if review.get("verdict") == "approve" else "FAIL", f"verdict {review.get('verdict')}, {len(review.get('changes', []))} changes"):
        return _fill(rows)
    problems, missing = [], []
    for name, which in (("flux_explanations", "flux"), ("client_questions", "questions")):
        p = d / f"{name}_{month}.md"
        if not p.is_file():
            missing.append(p.name)
        else:
            t = p.read_text(encoding="utf-8")
            problems += (gw.grade_flux(t, flux) if which == "flux" else gw.grade_questions(t, flux, review, packet))
    if not (d / f"monthly_review_{month}.xlsx").is_file():
        missing.append(f"monthly_review_{month}.xlsx")
    if missing:
        done(4, "NOT RUN", "missing: " + ", ".join(missing))
        return _fill(rows)
    if not done(4, "PASS" if not problems else "FAIL", "pack + flux notes + client questions graded" if not problems else "; ".join(problems[:2])):
        return _fill(rows)
    appr = _json(d / f"approval_{month}.json")
    if appr is None:
        done(5, "WAITING", "no human decision yet; run scripts/approve.py")
    else:
        done(5, "PASS" if appr.get("status") == "approved" else "FAIL", f"{appr.get('status')} by {appr.get('reviewer')}")
    return _fill(rows)


def _fill(rows):
    while len(rows) < len(STAGES):
        rows.append((STAGES[len(rows)], "NOT RUN", "an earlier stage did not pass"))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client"), ap.add_argument("month")
    ap.add_argument("--outputs-root", type=Path, default=ROOT / "outputs")
    a = ap.parse_args(argv)
    rows = evaluate(a.outputs_root / a.client, a.month)
    print(f"| # | Stage | Status | Note |\n|---|---|---|---|")
    for i, (s, st, n) in enumerate(rows, 1):
        print(f"| {i} | {s} | {st} | {n} |")
    first = next((r for r in rows if r[1] != "PASS"), None)
    print(f"\nStopped at: {first[0]} ({first[1]})" if first else "\nAll six stages passed.")
    return 0 if first is None else 1


if __name__ == "__main__":
    sys.exit(main())
