"""Trigger evals: does each skill / command fire for the requests it should, and stay quiet for the one it should not?

  python 03_evals/run_trigger_evals.py            # structure check only: 3+ positive and 1+ negative case per entry, names exist
  python 03_evals/run_trigger_evals.py --live     # also ask `claude -p` to route every case, one call per case
  python 03_evals/run_trigger_evals.py --live --only flux-explanations client-questions

Live routing: the model sees every skill and command name with its description (read from .claude/) and the request, and
answers with one name or NONE. A positive case passes when the answer is the entry; a negative passes when it is not.
Results (pass rate and every answer) go to outputs/trigger_eval_results.json. Exit 0 only when everything passes.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "03_evals" / "skill_triggers"
RESULTS = ROOT / "outputs" / "trigger_eval_results.json"
ROUTER = (
    "You route requests to skills and slash commands. Below is the list (name: description). For the request, answer with "
    "exactly one name from the list that you would invoke first, or NONE if none fits. Answer with the name only.\n\n"
    "{catalog}\n\nRequest: {prompt}"
)


def catalog() -> dict[str, str]:
    out = {}
    for p in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        m = re.search(r"^description:\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        if m:
            out[p.parent.name] = m.group(1).strip()
    for p in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        m = re.search(r"^description:\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        out[p.stem] = ("Slash command. " + m.group(1).strip()) if m else "Slash command."
    return out


def structure_problems(entry: dict, names: set[str]) -> list[str]:
    cs = entry["cases"]
    pos = sum(c["should_trigger"] for c in cs)
    neg = len(cs) - pos
    probs = []
    if entry["name"] not in names:
        probs.append(f"{entry['name']}: no such skill or command in .claude/")
    if pos < 3:
        probs.append(f"{entry['name']}: {pos} positive cases, need 3")
    if neg < 1:
        probs.append(f"{entry['name']}: no negative case")
    if len({c["prompt"] for c in cs}) != len(cs):
        probs.append(f"{entry['name']}: duplicate prompts")
    return probs


def route(claude: str, cat: dict[str, str], prompt: str) -> str:
    text = "\n".join(f"- {k}: {v}" for k, v in cat.items())
    # The prompt goes on stdin: on Windows the `claude` shim cuts a multi-line argument at the first newline, which made
    # every answer NONE in the 2026-10-14 run (44/44 NONE, 11/44 "passed" only because negatives pass on NONE).
    r = subprocess.run([claude, "-p"], input=ROUTER.format(catalog=text, prompt=prompt), cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed ({r.returncode}): {r.stderr[-300:]}")
    ans = r.stdout.strip().splitlines()[-1].strip().strip("`*/ .") if r.stdout.strip() else ""
    return ans


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    cat = catalog()
    entries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES.glob("*.json"))]
    if a.only:
        entries = [e for e in entries if e["name"] in a.only]
    problems = [p for e in entries for p in structure_problems(e, set(cat))]
    for p in problems:
        print("STRUCTURE:", p)
    print(f"structure: {len(entries)} entries, {len(problems)} problems")
    if not a.live:
        return 1 if problems else 0
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("Claude Code CLI not found on PATH.")
    results, passed, total = [], 0, 0
    for e in entries:
        ok_e = 0
        for c in e["cases"]:
            ans = route(claude, cat, c["prompt"])
            ok = (ans == e["name"]) if c["should_trigger"] else (ans != e["name"])
            total += 1
            passed += ok
            ok_e += ok
            results.append({"entry": e["name"], "prompt": c["prompt"], "should_trigger": c["should_trigger"], "answer": ans, "pass": ok})
            if not ok:
                print(f"FAIL {e['name']}: {c['prompt'][:70]!r} -> {ans}")
        print(f"{e['name']}: {ok_e}/{len(e['cases'])}")
    print(f"\ntrigger evals: {passed}/{total} ({passed / total:.0%})")
    RESULTS.write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "passed": passed, "total": total,
                                   "results": results}, indent=2), encoding="utf-8")
    return 0 if passed == total and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
