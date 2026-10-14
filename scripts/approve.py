"""Record a human Approve / Reject decision for one client period.

    python scripts/approve.py abc 2026-06 --reviewer "Name" --reason "Why" [--reject]

Writes outputs/<client>/approval_<period>.json and appends to outputs/<client>/audit_log.jsonl.
Rules: reviewer name and reason are required; approving needs the finance-reviewer verdict to be
"approve"; once a period is approved it is locked and no further decision is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "outputs"
CLIENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def fail(msg: str, code: int = 1) -> int:
    print(f"ERROR: {msg}")
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client"), ap.add_argument("period")
    ap.add_argument("--reviewer", required=True), ap.add_argument("--reason", required=True)
    ap.add_argument("--reject", action="store_true")
    a = ap.parse_args()
    if not CLIENT.match(a.client) or not PERIOD.match(a.period):
        return fail("invalid client or period", 2)
    reviewer, reason = a.reviewer.strip(), a.reason.strip()
    if not reviewer or not reason:
        return fail("reviewer name and reason must not be empty", 2)
    d = OUT / a.client
    packet, review = d / f"review_packet_{a.period}.json", d / f"review_{a.period}.json"
    path = d / f"approval_{a.period}.json"
    if not packet.is_file():
        return fail(f"no review packet for {a.client} {a.period}; run the pipeline first")
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        verdict = json.loads(review.read_text(encoding="utf-8")).get("verdict") if review.is_file() else None
    except ValueError as exc:  # never guess a decision from a damaged file
        return fail(f"cannot read an existing decision or verdict file as JSON ({exc.__class__.__name__}); "
                    f"check {path.name} and {review.name} in outputs/{a.client}/. Nothing was recorded.", 5)
    if existing.get("status") == "approved":
        return fail(f"{a.client} {a.period} is approved and locked", 3)
    status = "rejected" if a.reject else "approved"
    if status == "approved" and verdict != "approve":
        return fail(f"cannot approve: finance-reviewer verdict is {verdict!r}, not 'approve'", 4)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {"client": a.client, "period": a.period, "status": status, "reviewer": reviewer, "reason": reason,
              "decided_at": now, "review_verdict": verdict,
              "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest()}
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    with open(d / "audit_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now, "event": f"period_{status}", "client": a.client, "period": a.period,
                            "actor": reviewer, "reason": reason, "status": status}) + "\n")
    print(f"{a.client} {a.period}: {status} by {reviewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
