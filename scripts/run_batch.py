"""Run every client in clients/batch.yaml, each in its own subprocess with its own outputs root and temp dir.

    python scripts/run_batch.py [--root DIR] [--jobs N] [--only abc c04]

Client <id> runs `scripts/run_pipeline.py <id> <month> --outputs-root <root>/<id>` with TMP/TEMP/TMPDIR set to
<root>/<id>/.proc_tmp, so no two clients share an outputs root or a temp folder. Prints a table (client, status,
months, warnings, seconds), writes <root>/batch_results.json, and exits 1 if any client's outcome differs from what
clients/batch.yaml declares (a declared refusal that happens is not a failure). One client's failure does not stop the others.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[1]
BATCH = PROJECT / "clients" / "batch.yaml"


def run_one(client: str, spec: dict, root: Path, clients_root: Path) -> dict:
    out_root = root / client
    tmp = out_root / ".proc_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("QUICKBOOKS_")}
    env.update(TMP=str(tmp), TEMP=str(tmp), TMPDIR=str(tmp))
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-X", "utf8", str(PROJECT / "scripts" / "run_pipeline.py"), client, str(spec["month"]),
                        "--clients-root", str(clients_root), "--outputs-root", str(out_root)],
                       cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    secs = round(time.monotonic() - t0, 1)
    summary = out_root / client / "summary.json"
    s = json.loads(summary.read_text(encoding="utf-8")) if summary.is_file() and p.returncode == 0 else {}
    warnings = s.get("warnings", [])
    status = "success" if p.returncode == 0 else "refused"
    ok = status == spec.get("expect", "success") and (not spec.get("warn") or any(spec["warn"] in w for w in warnings))
    err = next((l.strip() for l in p.stdout.splitlines() if "failed" in l and " - " in l), "")
    return {"client": client, "month": str(spec["month"]), "status": status, "expected": spec.get("expect", "success"),
            "as_declared": ok, "months": s.get("months"), "warnings": len(warnings), "seconds": secs, "error": err[:300],
            "outputs_root": str(out_root)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=PROJECT / "outputs" / "_batch" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    ap.add_argument("--clients-root", type=Path, default=PROJECT / "clients")
    ap.add_argument("--batch", type=Path, default=BATCH)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", nargs="+")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    specs = yaml.safe_load(args.batch.read_text(encoding="utf-8"))
    clients = [c for c in specs if not args.only or c in args.only]
    args.root.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(lambda c: run_one(c, specs[c], args.root, args.clients_root), clients))
    total = round(time.monotonic() - t0, 1)
    print("| client | status | declared | months | warnings | seconds |\n|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['client']} | {r['status']} | {r['expected']}{'' if r['as_declared'] else ' **MISMATCH**'} | {r['months']} | {r['warnings']} | {r['seconds']} |")
    bad = [r for r in rows if not r["as_declared"]]
    print(f"\n{len(rows)} clients, {len(rows) - len(bad)} as declared, total {total}s with {args.jobs} parallel jobs."
          + (" Unexpected: " + ", ".join(f"{r['client']} ({r['error'] or r['status']})" for r in bad) if bad else ""))
    (args.root / "batch_results.json").write_text(json.dumps({"total_seconds": total, "jobs": args.jobs, "rows": rows}, indent=2), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
