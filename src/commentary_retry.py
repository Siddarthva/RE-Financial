"""Grade the drafted commentary; on failure, send the grader's exact mismatches back to the skill ONCE, then re-grade.

    python src/commentary_retry.py grade   <client> <YYYY-MM>   # attempt 1: grades outputs/<client>/commentary_<month>.md
    python src/commentary_retry.py regrade <client> <YYYY-MM>   # attempt 2, only after a failed attempt 1 and one revision
    python src/commentary_retry.py final   <client> <YYYY-MM>   # grades the final text once more into commentary_final_grade_<month>.json;
                                                                 # not an attempt, the attempt record is left alone
Every action takes --outputs-root DIR (default outputs/).

Both write outputs/<client>/commentary_grade_<month>.json and print the mismatches. Outcomes:
  passed_first        attempt 1 passed (no retry);
  retry_pending       attempt 1 failed; the printed mismatches go back to the skill for ONE correction;
  passed_after_retry  attempt 2 passed;
  NOT APPROVED        attempt 2 failed too: needs_human is true and the reasons are recorded. The pack shows it.
There is never a third attempt, and nothing here approves a pack: approval stays with a human (scripts/approve.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SRC.parent / "03_evals"))
import run_client  # noqa: E402
from client_sandbox import client_sandbox  # noqa: E402
from grade_commentary import grade  # noqa: E402

MAX_ATTEMPTS = 2


def mismatches(report: dict) -> list[str]:
    """The grader's failures, one line each, in words the skill can act on."""
    out = [f"Number '{n['token']}' ({n['kind']}) matches no value in the review packet" for n in report["numbers"] if not n["matched"]]
    if not report["numbers"]:
        out.append("The commentary states no numbers from the review packet")
    out += [f"Top movement not mentioned: {m['account']} ({m['mom_change']:+,.2f})" for m in report["top_movements"] if not m["mentioned"]]
    cash = report["cash_risk"]
    if not cash["covered"]:
        if not cash.get("cash_stated"):
            out.append("Cash balance from the packet is not stated")
        if not cash.get("runway_stated"):
            out.append("Runway from the packet is not stated")
    s = report.get("sections") or {}
    if s and not s.get("passed"):
        out.append("Sections missing: " + ", ".join(s["missing"]) if s.get("missing") else "Sections out of order")
    return out


def attempt(text: str, packet: dict) -> dict:
    report = grade(text, packet, require_sections=True)
    return {"passed": bool(report["passed"]), "mismatches": mismatches(report),
            "numbers": f"{report['numbers_matched']}/{report['numbers_checked']}"}


def outcome(attempts: list[dict]) -> dict:
    """Status from the attempts so far. Never returns an approval."""
    first = attempts[0]
    if first["passed"]:
        return {"status": "passed_first", "retry_used": False, "needs_human": False, "reasons": []}
    if len(attempts) == 1:
        return {"status": "retry_pending", "retry_used": False, "needs_human": False, "reasons": first["mismatches"]}
    last = attempts[-1]
    if last["passed"]:
        return {"status": "passed_after_retry", "retry_used": True, "needs_human": False, "reasons": []}
    return {"status": "NOT APPROVED", "retry_used": True, "needs_human": True, "reasons": last["mismatches"]}


def grade_with_retry(text: str, packet: dict, revise) -> dict:
    """The whole loop in one call (used by tests): grade, at most one revise(text, mismatches) -> text, re-grade."""
    attempts = [attempt(text, packet)]
    if not attempts[0]["passed"]:
        text = revise(text, list(attempts[0]["mismatches"]))
        attempts.append(attempt(text, packet))
    return {**outcome(attempts), "attempts": attempts, "final_text": text}


def record_path(out_dir: Path, month: str) -> Path:
    return out_dir / f"commentary_grade_{month}.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["grade", "regrade", "final"])
    ap.add_argument("client"), ap.add_argument("month")
    ap.add_argument("--outputs-root", type=Path, default=run_client.OUTPUTS_ROOT)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with client_sandbox(args.client, run_client.CLIENTS_ROOT, args.outputs_root):
        out_dir = Path(args.outputs_root) / args.client
        packet = json.loads((out_dir / f"review_packet_{args.month}.json").read_text(encoding="utf-8"))
        text = (out_dir / f"commentary_{args.month}.md").read_text(encoding="utf-8")
        if args.action == "final":
            last = attempt(text, packet)
            (out_dir / f"commentary_final_grade_{args.month}.json").write_text(json.dumps(
                {"client": args.client, "period": args.month, "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **last},
                indent=2), encoding="utf-8")
            print(f"Final grade: {'PASS' if last['passed'] else 'FAIL'} (numbers {last['numbers']})")
            for m in last["mismatches"]:
                print(f"  - {m}")
            return 0 if last["passed"] else 1
        rec_path = record_path(out_dir, args.month)
        prior = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.is_file() else None
        if args.action == "grade":
            attempts = [attempt(text, packet)]
        else:
            if not prior or prior.get("status") != "retry_pending":
                print("regrade is only allowed once, after a failed first grade (status retry_pending).")
                return 2
            attempts = prior["attempts"] + [attempt(text, packet)]
        result = {"client": args.client, "period": args.month, "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  **outcome(attempts), "attempts": attempts}
        rec_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Attempt {len(attempts)}: {'PASS' if attempts[-1]['passed'] else 'FAIL'} (numbers {attempts[-1]['numbers']}); status: {result['status']}")
    for m in attempts[-1]["mismatches"]:
        print(f"  - {m}")
    if result["status"] == "retry_pending":
        print("Fix exactly these items in the commentary ONCE, then run: python src/commentary_retry.py regrade "
              f"{args.client} {args.month}")
    if result["needs_human"]:
        print("NOT APPROVED: needs human. The pack will show these reasons; do not retry again.")
    return 0 if result["status"] in ("passed_first", "passed_after_retry") else 1


if __name__ == "__main__":
    sys.exit(main())
