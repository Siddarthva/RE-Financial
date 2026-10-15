"""Grade the outputs of the `flux-explanations` and `client-questions` skills against the engine's JSON.

Python holds every number; these graders only check that the skills' text uses those numbers and follows the rules.

  python 03_evals/grade_workflow_skills.py flux     <client> <YYYY-MM> [--file FILE]
  python 03_evals/grade_workflow_skills.py questions <client> <YYYY-MM> [--file FILE]

flux-explanations (outputs/<client>/flux_explanations_<month>.md), one numbered line per flagged item:
  - every flagged item in flux_<month>.json appears exactly once, with its source cell;
  - every number is the item's own (current, prior, change, %), a numbered same-section item's, or the rule's threshold;
  - no causal words; exactly one question (one "?") per item.
client-questions (outputs/<client>/client_questions_<month>.md), one table row per request:
  - Source cites flux:<account>, reviewer:<n> (review_<month>.json open_questions) or auto:cash (runway under 6 months);
  - every flagged item, every reviewer question and the cash flag is covered; no duplicate rows;
  - priority follows materiality: High if a linked flux item moves >= 10,000 or the source is auto:cash, else Medium;
  - every number is one of the packet / flux numbers.
Exit 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
HIGH_DOLLARS = 10_000.0
RUNWAY_WARN_MONTHS = 6
CAUSAL = re.compile(
    r"\b(because|due to|driven by|caused by|as a result of|resulting from|result of|owing to|attributable to|"
    r"led to|thanks to|on account of|reflects?|reflecting|explained by|so that)\b", re.I)
CELL_REF = re.compile(r"[A-Za-z][A-Za-z ]*!\$?[A-Z]{1,3}\$?\d+")
NUMBER = re.compile(r"(?<![\w.])[-+−–]?\$?\d[\d,]*(?:\.\d+)?%?")
LINE = re.compile(r"^\s*(\d+)\.\s+(.*)$")


def numbers_in(text: str, names: list[str]) -> list[tuple[float, bool, bool]]:
    """(value, is_percent, has_decimals) for every number in text, ignoring cell refs, account names and list numbers."""
    for n in sorted(names, key=len, reverse=True):
        text = text.replace(n, " ")
    text = CELL_REF.sub(" ", text)
    out = []
    for m in NUMBER.finditer(text):
        raw = m.group(0)
        pct = raw.endswith("%")
        body = raw.rstrip("%").replace("$", "").replace(",", "").replace("−", "-").replace("–", "-").replace("+", "")
        try:
            out.append((float(body), pct, "." in body))
        except ValueError:
            pass
    return out


def allowed_for(item: dict) -> tuple[set[float], set[float]]:
    money = {item["current"], item["prior"], item["dollar_change"]}
    pct = {round(item["pct_change"] * 100, 1)} if item.get("pct_change") is not None else set()
    return {abs(x) for x in money}, {abs(x) for x in pct}


def number_problems(text: str, names: list[str], items: list[dict], extra: set[float] = frozenset()) -> list[str]:
    money, pcts = set(extra), set()
    for it in items:
        m, p = allowed_for(it)
        money |= m
        pcts |= p
    bad = []
    for value, is_pct, has_dec in numbers_in(text, names):
        v = abs(value)
        if is_pct:
            ok = any(abs(v - p) <= (0.051 if has_dec else 0.51) for p in pcts)
        else:
            ok = any(abs(v - m) <= (0.006 if has_dec else 0.51) for m in money)
        if not ok:
            bad.append(f"{value:g}{'%' if is_pct else ''}")
    return bad


def load(client: str, month: str):
    d = OUT / client
    flux = json.loads((d / f"flux_{month}.json").read_text(encoding="utf-8"))
    return d, flux


def rule_numbers(flux: dict) -> set[float]:
    r = flux["rule"]
    return {r["min_dollars"], r["sign_flip_dollars"], r["min_pct"] * 100}


def grade_flux(text: str, flux: dict) -> list[str]:
    items = flux["items"]
    extra = rule_numbers(flux)
    problems = []
    lines = [(int(m.group(1)), m.group(2)) for ln in text.splitlines() if (m := LINE.match(ln))]
    if [n for n, _ in lines] != list(range(1, len(lines) + 1)):
        problems.append("lines must be numbered 1., 2., 3. ... in order")
    names = [it["account"] for it in items]
    seen = {}
    for n, body in lines:
        hits = [it for it in items if it["account"] in body]
        # the line's subject is the account named first
        subject = min(hits, key=lambda it: body.index(it["account"])) if hits else None
        if subject is None:
            problems.append(f"line {n}: names no flagged account")
            continue
        acct = subject["account"]
        seen[acct] = seen.get(acct, 0) + 1
        if subject["source_cell_current"] not in body:
            problems.append(f"line {n} ({acct}): source cell {subject['source_cell_current']} missing")
        if CAUSAL.search(body):
            problems.append(f"line {n} ({acct}): causal wording '{CAUSAL.search(body).group(0)}'")
        if body.count("?") != 1:
            problems.append(f"line {n} ({acct}): needs exactly one question, found {body.count('?')}")
        bad = number_problems(body, names, items, extra)
        if bad:
            problems.append(f"line {n} ({acct}): numbers not in the flux file: {', '.join(bad)}")
    for it in items:
        c = seen.get(it["account"], 0)
        if c != 1:
            problems.append(f"{it['account']}: expected 1 line, found {c}")
    return problems


def parse_rows(text: str) -> list[dict]:
    rows = []
    header = None
    for ln in text.splitlines():
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def grade_questions(text: str, flux: dict, review: dict, packet: dict) -> list[str]:
    items = {it["account"]: it for it in flux["items"]}
    rows = parse_rows(text)
    problems = []
    need = ("item", "source", "request", "why it matters", "document needed", "priority")
    if not rows or any(k not in rows[0] for k in need):
        return [f"table must have columns: {', '.join(need)}"]
    covered_flux, covered_rev, covered_cash = set(), set(), False
    seen_req, seen_key = set(), set()
    cash = packet.get("cash") or {}
    runway = (cash.get("runway_months") or {}).get(cash.get("primary_window"))
    extra = rule_numbers(flux) | {HIGH_DOLLARS, float(RUNWAY_WARN_MONTHS)}
    n_rev = len(review.get("open_questions", []))
    for i, r in enumerate(rows, 1):
        linked = []
        for src in [s.strip() for s in r["source"].split(";") if s.strip()]:
            if src.startswith("flux:") and src[5:] in items:
                covered_flux.add(src[5:])
                linked.append(items[src[5:]])
            elif src.startswith("reviewer:") and src[9:].isdigit() and 1 <= int(src[9:]) <= n_rev:
                covered_rev.add(int(src[9:]))
            elif src == "auto:cash" and runway is not None and runway < RUNWAY_WARN_MONTHS:
                covered_cash = True
            else:
                problems.append(f"row {i}: source '{src}' traces to no flagged item, reviewer note or cash flag")
        if not r["source"].strip():
            problems.append(f"row {i}: empty source")
        for col in ("request", "why it matters", "document needed"):
            if not r[col]:
                problems.append(f"row {i}: empty {col}")
        key, req = (r["item"].lower(), r["source"].lower()), norm(r["request"])
        if key in seen_key or req in seen_req:
            problems.append(f"row {i}: duplicate of an earlier row")
        seen_key.add(key), seen_req.add(req)
        if CAUSAL.search(r["request"] + " " + r["why it matters"]):
            problems.append(f"row {i}: causal wording '{CAUSAL.search(r['request'] + ' ' + r['why it matters']).group(0)}'")
        want = "High" if ("auto:cash" in r["source"] or any(abs(it["dollar_change"]) >= HIGH_DOLLARS for it in linked)) else "Medium"
        if r["priority"] != want:
            problems.append(f"row {i}: priority {r['priority']}, materiality rule gives {want}")
        burn = (cash.get("burn") or {}).get(cash.get("primary_window")) or 0
        cash_extra = {cash.get("value", 0), runway or 0, round(runway or 0, 1), burn}
        rev_extra = {abs(x) for x in _numbers_of_review(review)}
        bad = number_problems(r["request"] + " " + r["why it matters"], list(items), list(items.values()),
                              extra | cash_extra | rev_extra)
        if bad:
            problems.append(f"row {i}: numbers not in the packet, flux or review files: {', '.join(bad)}")
    for a in items:
        if a not in covered_flux:
            problems.append(f"flagged item not requested: {a}")
    for n in range(1, n_rev + 1):
        if n not in covered_rev:
            problems.append(f"reviewer question {n} not requested")
    if runway is not None and runway < RUNWAY_WARN_MONTHS and not covered_cash:
        problems.append("cash flag (runway under 6 months) not requested")
    return problems


def _numbers_of_review(review: dict) -> list[float]:
    out = []
    for q in review.get("open_questions", []):
        for v, _, _ in numbers_in(q.get("question", "") + " " + q.get("why", ""), []):
            out.append(v)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["flux", "questions"])
    ap.add_argument("client"), ap.add_argument("month")
    ap.add_argument("--file")
    a = ap.parse_args(argv)
    d, flux = load(a.client, a.month)
    name = "flux_explanations" if a.which == "flux" else "client_questions"
    path = Path(a.file) if a.file else d / f"{name}_{a.month}.md"
    if not path.is_file():
        print(f"FAIL: {path} not found")
        return 1
    text = path.read_text(encoding="utf-8")
    if a.which == "flux":
        problems = grade_flux(text, flux)
    else:
        review = json.loads((d / f"review_{a.month}.json").read_text(encoding="utf-8"))
        packet = json.loads((d / f"review_packet_{a.month}.json").read_text(encoding="utf-8"))
        problems = grade_questions(text, flux, review, packet)
    for p in problems:
        print("  -", p)
    print(f"{a.which}: {'PASS' if not problems else 'FAIL'} ({len(problems)} problems)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
