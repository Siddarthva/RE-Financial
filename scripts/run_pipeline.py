"""Run the deterministic stages of the monthly close for one client and month, and write a run manifest.

    python scripts/run_pipeline.py abc 2026-06 [--clients-root DIR --outputs-root DIR]

Stages run here: Intake (workbook hash + checks) -> Calculate (existing src/monthly_review.py prepare,
then the flux table). The later stages (Skill draft, Review, Package) are done by the
/monthly-analysis command; their status is read from the files they leave behind.
Writes only under outputs/<client>/. Refuses to re-run a period that has been approved (locked).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import abc_workbook_adapter as engine  # noqa: E402
import close_artifacts as ca  # noqa: E402
import monthly_review  # noqa: E402
import run_client  # noqa: E402
from client_sandbox import client_sandbox  # noqa: E402

OUT = run_client.OUTPUTS_ROOT
SKILL = PROJECT / ".claude" / "skills" / "monthly-financial-analysis" / "SKILL.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_sha() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def flatten(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from flatten(v, f"{prefix}{k}.")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from flatten(v, f"{prefix}{i}.")
    else:
        yield prefix.rstrip("."), node


def diff_packets(old: dict, new: dict, limit: int = 200) -> list[dict]:
    a, b = dict(flatten(old)), dict(flatten(new))
    out = [{"path": k, "old": a.get(k), "new": b.get(k)} for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    return out[:limit]


def audit(out_dir: Path, event: dict) -> None:
    with open(out_dir / "audit_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), **event}) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client"), ap.add_argument("month")
    # Other roots: used by 03_evals/robustness to run on corrupted copies without touching clients/ or outputs/.
    ap.add_argument("--clients-root", type=Path, default=run_client.CLIENTS_ROOT)
    ap.add_argument("--outputs-root", type=Path, default=OUT)
    args = ap.parse_args(argv)
    client, month, clients_root, outputs_root = args.client, args.month, args.clients_root, args.outputs_root
    sys.stdout.reconfigure(encoding="utf-8")
    # Validate before any path is built: a client like '../x' would otherwise write outside the outputs folder.
    if not run_client.CLIENT_ID.match(client):
        print(f"ERROR: invalid client id {client!r}; use lowercase letters, digits, '-' or '_' (e.g. abc).")
        return 2
    if not monthly_review.MONTH.match(month):
        print(f"ERROR: month must look like 2026-06, got {month!r}.")
        return 2
    if not (Path(clients_root) / client / "config.yaml").is_file():
        print(f"ERROR: unknown client {client!r}: no {Path(clients_root) / client / 'config.yaml'}. Add a config (see 02_skill/README.md).")
        return 2
    out_dir = outputs_root / client
    approval = out_dir / f"approval_{month}.json"
    if approval.is_file() and json.loads(approval.read_text(encoding="utf-8")).get("status") == "approved":
        print(f"{client} {month} is approved and locked; not re-running.")
        return 3

    started = datetime.now(timezone.utc)
    run_id = f"{started:%Y%m%dT%H%M%SZ}-{client}-{month}"
    sha = git_sha()
    skill_version = f"monthly-financial-analysis@{hashlib.sha256(SKILL.read_bytes()).hexdigest()[:12]}" if SKILL.is_file() else None
    stages, status, source = [], "success", None
    packet_path = out_dir / f"review_packet_{month}.json"
    old_packet = json.loads(packet_path.read_text(encoding="utf-8")) if packet_path.is_file() else None
    prev = sorted(out_dir.glob(f"manifest_*-{client}-{month}.json")) if out_dir.is_dir() else []
    prev_id = json.loads(prev[-1].read_text(encoding="utf-8"))["run_id"] if prev else None

    def stage(name, fn):
        t0 = time.monotonic()
        try:
            fn()
            stages.append({"name": name, "status": "done", "duration_s": round(time.monotonic() - t0, 3)})
            return True
        except Exception as exc:  # report the stage failure; message is from our own engine, not secrets
            stages.append({"name": name, "status": "failed", "duration_s": round(time.monotonic() - t0, 3),
                           "error": f"{type(exc).__name__}: {exc}"})
            return False

    ctx = {}

    def intake():
        nonlocal source
        with client_sandbox(client, clients_root, outputs_root):
            cfg = run_client.load_config(client, clients_root)
            report, am, loc = ca.intake_gate(cfg, month, engine)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"intake_{month}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            tables = ca.build_tables(cfg, am, engine)
            (out_dir / f"tables_{month}.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
            ctx["loc"], source = loc, {"workbook": report["workbook"], "sha256": report["sha256"]}
            refused = ca.refusal(report, month)
            if refused:
                raise ValueError(refused)

    def calculate():
        # prepare writes the packet, the intake report and the flux table (with the client's materiality threshold).
        monthly_review.prepare(client, month, clients_root, outputs_root)

    def grade_commentary():
        # Re-grade an existing commentary draft against the fresh packet, using the existing grader.
        text_path = out_dir / f"commentary_{month}.md"
        if not text_path.is_file():
            return
        import importlib.util
        spec = importlib.util.spec_from_file_location("grade_commentary", PROJECT / "03_evals" / "grade_commentary.py")
        gc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gc)
        text = text_path.read_text(encoding="utf-8")
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        report = gc.grade(text, packet, require_sections=True)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        (out_dir / f"commentary_{month}.json").write_text(
            json.dumps({"period": month, "lines": lines, "grade": report}, indent=2, default=str), encoding="utf-8")

    ok = stage("Intake", intake) and stage("Calculate", calculate)
    if ok:
        stage("Grade commentary", grade_commentary)
    if not ok:
        status = "failed"

    diff = None
    if status == "success" and old_packet is not None and prev_id:
        new_packet = json.loads(packet_path.read_text(encoding="utf-8"))
        diff = {"previous_run_id": prev_id, "changed": diff_packets(old_packet, new_packet)}

    manifest = {
        "run_id": run_id, "client": client, "period": month, "started_at": started.isoformat(timespec="seconds"),
        "finished_at": now(), "source": source, "skill_version": skill_version, "git_sha": sha,
        "status": status, "stages": stages, "diff_vs_previous": diff,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"manifest_{run_id}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    audit(out_dir, {"event": "pipeline_run", "run_id": run_id, "client": client, "period": month, "status": status, "actor": "pipeline"})
    print(f"{run_id}: {status}")
    for s in stages:
        print(f"  {s['name']}: {s['status']} ({s['duration_s']}s){' - ' + s['error'] if s.get('error') else ''}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
