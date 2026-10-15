"""Grade financial commentary against the engine's computed numbers for the ABC workbook.

Every number in the commentary must match a computed value (within display rounding), and the
top 3 latest-month line-item movements by absolute change must be named, and the cash risk (cash
balance plus runway) must be stated. See 03_evals/GRADING.md.

Usage:
  python 03_evals/grade_commentary.py                     # grade the adapter's own generate_commentary()
  python 03_evals/grade_commentary.py --commentary FILE   # grade any commentary text (e.g. a skill run)
  python 03_evals/grade_commentary.py --run-skill         # run the monthly-financial-analysis skill headless, then grade
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import abc_workbook_adapter as abc  # noqa: E402

WORKBOOK = ROOT / "data" / "ABC Inc - Financial Statements.xlsx"
OUTPUTS = ROOT / "outputs"
METRICS = ["revenue", "cost_of_goods_sold", "gross_profit", "operating_expenses", "operating_income", "net_income"]
MARGINS = {"gross_profit": "gross_margin_pct", "operating_income": "operating_margin_pct", "net_income": "net_margin_pct"}
SKILL_PROMPT = (
    "Use the monthly-financial-analysis skill. Run the engine on 'ABC Inc - Financial Statements.xlsx' "
    "(read-only; write any files only under outputs) and write the executive commentary for the latest month. "
    "Print only the final commentary text."
)


def build_computed():
    """Engine output as JSON for the ABC workbook's latest month (shared builder: src/monthly_review.py)."""
    import monthly_review as mr  # imported here: monthly_review imports this module
    import run_client
    am = abc.parse_wide_income_statement(WORKBOOK)
    monthly = abc.build_monthly_summary(am).set_index("month")
    cash = abc.cash_position(abc.parse_wide_income_statement(WORKBOOK, abc.ABC_BS_LAYOUT))
    packet = mr.build_computed(am, monthly, monthly.index[-1], cash, categories=mr.rollup_categories(am, run_client.load_config("abc")))
    return mr.add_one_offs(packet, am)


def fact_pools(computed):
    """Flatten computed JSON into magnitudes by unit: amounts, percents (x100), percentage points."""
    amounts, percents, points = [], [], []
    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            if key in {"mom_pct", "margin", "ttm_margin", "share_of_opex", "yoy_pct", "prior_margin"}:
                percents.append(abs(node) * 100)
            elif key in {"margin_change_pp", "yoy_change_pp"}:
                points.append(abs(node))
            else:
                amounts.append(abs(node))
    walk(computed["months"])
    walk(computed["line_items"])
    walk(computed.get("cash", {}))
    walk(computed.get("yoy", {}))
    walk(computed.get("adjusted_net_income", {}))
    walk({o["account"]: o["amount"] for o in computed.get("one_offs", [])})
    return {"amount": amounts, "percent": percents, "pp": points}


RUNWAY_FIGURE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?months?\b", re.I)


def check_cash_risk(text, numbers, cash):
    """Cash risk is covered only if the commentary states the cash balance, says 'runway', and gives a runway figure."""
    if not cash:  # no Balance Sheet cash for this client: nothing to cover
        return {"covered": True, "applicable": False, "cash_stated": False, "runway_stated": False}
    cash_stated = any(n["kind"] == "amount" and abs(n["value"] - cash["value"]) <= n["tol"] for n in numbers)
    runways = [v for v in cash["runway_months"].values() if v is not None]
    # Runway figures are often small whole numbers ("about 3 months"), which number extraction skips, so read them here.
    figures = [(float(m.group(1)), 0.5 * 10 ** -(len(m.group(1).split(".")[1]) if "." in m.group(1) else 0))
               for m in RUNWAY_FIGURE.finditer(text)]
    runway_stated = "runway" in text.casefold() and any(abs(f - r) <= tol + 1e-9 for f, tol in figures for r in runways)
    return {"covered": cash_stated and runway_stated, "cash_stated": cash_stated, "runway_stated": runway_stated,
            "cash": cash["value"], "runway_months": cash["runway_months"]}


# Commentary section order (see the monthly-financial-analysis skill, section 9). A heading counts when its text
# contains the section's key words; "and" and "&" are interchangeable.
SECTIONS = [("Headline", "headline"), ("Revenue", "revenue"), ("Margins", "margin"), ("Opex", "opex|operating expenses"),
            ("Cash & runway", "cash"), ("One-offs", "one-off|one off"), ("Questions", "question")]


def check_sections(text, sections=SECTIONS):
    """Markdown headings (## ...) must include every section, in order. Returns found/missing/order for the report."""
    heads = [h.strip().casefold().replace(" and ", " & ") for h in re.findall(r"^\s*#{1,6}\s+(.+?)\s*$", text, re.M)]
    found, last, in_order = [], -1, True
    for name, pattern in sections:
        idx = next((i for i, h in enumerate(heads) if re.search(pattern, h)), None)
        if idx is None:
            continue
        found.append(name)
        in_order = in_order and idx > last
        last = idx
    missing = [n for n, _ in sections if n not in found]
    return {"required": [n for n, _ in sections], "found": found, "missing": missing, "in_order": in_order,
            "passed": not missing and in_order}


MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
NUMBER = re.compile(
    r"(?P<sign>[-−+])?\s?(?P<cur>\$)?\(?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\)?"
    r"\s?(?P<unit>%|percentage points?|pp|percent|[kK]\b|M\b|million|thousand)?"
)
SCALE = {"k": 1e3, "K": 1e3, "thousand": 1e3, "M": 1e6, "million": 1e6}


def extract_numbers(text):
    """Yield (token, magnitude, unit, decimals) for numbers that make a financial claim.

    Skipped as non-claims: years (2000-2100, no comma/decimal), day/period counts and list markers
    (unitless integers < 100 with no '$', e.g. '12 months', '3 questions', '1.'), and day-of-month after a month name.
    """
    for m in NUMBER.finditer(text):
        raw, unit = m.group("num"), m.group("unit") or ""
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw.replace(",", ""))
        plain = not unit and not m.group("cur") and "," not in raw
        before = text[max(0, m.start() - 12):m.start()]
        if plain and decimals == 0 and 2000 <= value <= 2100:
            continue
        if plain and decimals == 0 and value < 100:
            continue
        if plain and re.search(MONTHS + r"\s*$", before):
            continue
        if unit in ("%", "percent"):
            kind = "percent"
        elif unit.startswith("percentage point") or unit == "pp":
            kind = "pp"
        else:
            kind = "amount"
            value *= SCALE.get(unit, 1)
        tol = 0.5 * 10 ** -decimals * SCALE.get(unit, 1) + 1e-9
        yield m.group(0).strip(), value, kind, tol


def grade(text, computed, require_sections=False):
    pools = fact_pools(computed)
    numbers = []
    for token, value, kind, tol in extract_numbers(text):
        match = next((f for f in pools[kind] if abs(f - value) <= tol), None)
        numbers.append({"token": token, "kind": kind, "value": value, "tol": tol, "matched": match is not None, "fact": match})
    low = text.casefold()
    movements = []
    for item in computed["top_movements"]:
        names = {item["account"].casefold(), item["account"].split(":")[-1].strip().casefold()}
        movements.append({**item, "mentioned": any(n in low for n in names)})
    cash_risk = check_cash_risk(text, numbers, computed.get("cash"))
    sections = check_sections(text)
    passed = (all(n["matched"] for n in numbers) and all(m["mentioned"] for m in movements) and bool(numbers)
              and cash_risk["covered"] and (sections["passed"] or not require_sections))
    return {"passed": passed, "sections": sections, "numbers_checked": len(numbers), "numbers_matched": sum(n["matched"] for n in numbers),
            "numbers": numbers, "top_movements": movements, "cash_risk": cash_risk}


# Owner memo: plain language, cash and runway first. Same number check as the commentary, no top-3 rule.
MEMO_SECTIONS = [("Cash & runway", "cash"), ("How the month went", "month"), ("Questions for you", "question")]
JARGON = re.compile(r"\b(MoM|YoY|TTM|EBITDA|COGS|opex|flux|pp|basis points?|YTD)\b", re.I)


def grade_memo(text, computed):
    """Memo passes when every number matches the packet, cash and runway are stated, the three sections appear in
    order with cash first, and no accounting shorthand is used."""
    pools = fact_pools(computed)
    numbers = []
    for token, value, kind, tol in extract_numbers(text):
        match = next((f for f in pools[kind] if abs(f - value) <= tol), None)
        numbers.append({"token": token, "kind": kind, "value": value, "matched": match is not None})
    cash_risk = check_cash_risk(text, [{**n, "tol": 0.5} for n in numbers], computed.get("cash"))
    sections = check_sections(text, MEMO_SECTIONS)
    jargon = sorted({m.group(0) for m in JARGON.finditer(text)})
    passed = (all(n["matched"] for n in numbers) and bool(numbers) and cash_risk["covered"] and sections["passed"] and not jargon)
    return {"passed": passed, "numbers_checked": len(numbers), "numbers_matched": sum(n["matched"] for n in numbers),
            "unmatched": [n["token"] for n in numbers if not n["matched"]], "cash_risk": cash_risk,
            "sections": sections, "jargon": jargon}


def run_skill():
    claude = shutil.which("claude")  # claude.cmd on Windows
    if not claude:
        raise SystemExit("Claude Code CLI not found on PATH.")
    result = subprocess.run([claude, "-p", SKILL_PROMPT, "--allowedTools", "Read", "Glob", "Grep", "Bash(python *)"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=900)
    if result.returncode != 0:
        raise SystemExit(f"Skill run failed ({result.returncode}): {result.stderr[-2000:]}")
    path = OUTPUTS / "skill_commentary.md"
    path.write_text(result.stdout, encoding="utf-8")
    return result.stdout, path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--commentary", type=Path, help="commentary text file to grade")
    src.add_argument("--run-skill", action="store_true", help="run the skill via `claude -p` and grade its output")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUTS.mkdir(exist_ok=True)

    computed = build_computed()
    (OUTPUTS / "abc_computed.json").write_text(json.dumps(computed, indent=2), encoding="utf-8")
    if args.commentary:
        text, label = args.commentary.read_text(encoding="utf-8"), str(args.commentary)
    elif args.run_skill:
        text, path = run_skill()
        label = f"skill run (saved to {path})"
    else:
        am = abc.parse_wide_income_statement(WORKBOOK)
        cash = abc.cash_position(abc.parse_wide_income_statement(WORKBOOK, abc.ABC_BS_LAYOUT))
        text, label = "\n".join(abc.generate_commentary(abc.build_monthly_summary(am), am, cash)), "engine generate_commentary()"

    report = grade(text, computed)
    (OUTPUTS / "commentary_grade.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Grading: {label}\nComputed JSON: {OUTPUTS / 'abc_computed.json'}\n")
    for n in report["numbers"]:
        print(f"  {'OK  ' if n['matched'] else 'MISS'} {n['kind']:<7} {n['token']}")
    print(f"\nNumbers: {report['numbers_matched']}/{report['numbers_checked']} match computed values")
    for m in report["top_movements"]:
        print(f"  {'OK  ' if m['mentioned'] else 'MISS'} top movement: {m['account']} ({m['mom_change']:+,.2f})")
    print(f"Top movements mentioned: {sum(m['mentioned'] for m in report['top_movements'])}/3")
    cr = report["cash_risk"]
    print(f"  {'OK  ' if cr['cash_stated'] else 'MISS'} cash balance stated ({cr.get('cash', 0):,.2f})")
    print(f"  {'OK  ' if cr['runway_stated'] else 'MISS'} runway stated (months: {cr.get('runway_months')})")
    print(f"Cash risk covered: {'yes' if cr['covered'] else 'no'}")
    sec = report["sections"]
    print(f"Sections present (order Headline, Revenue, Margins, Opex, Cash & runway, One-offs, Questions): "
          f"{'yes' if sec['passed'] else 'no - missing ' + ', '.join(sec['missing']) + ('' if sec['in_order'] else ' / out of order')}"
          " (informational for this report; required in the sign-off pack)")
    print(f"\nRESULT: {'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
