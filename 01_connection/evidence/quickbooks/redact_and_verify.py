"""Redact raw QuickBooks MCP responses into 01_connection/evidence/quickbooks/ and verify what they show.

    python 01_connection/evidence/quickbooks/redact_and_verify.py <raw_dir>

<raw_dir> holds the verbatim responses (kept outside the repo). For each call this writes
NN_name.request.json (exact tool + params) and NN_name.response.redacted.json|.txt, then
redaction_log.json (what was redacted, counts only) and checks.json (the claims these files prove).
It exits non-zero if any secret-like pattern survives redaction or any check fails.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = "quickbooks (local MCP, read-only: QUICKBOOKS_DISABLE_WRITE/UPDATE/DELETE=true)"
CALLS = [
    ("01_pnl_2026-01_to_06_monthly_accrual", "get_profit_and_loss",
     {"start_date": "2026-01-01", "end_date": "2026-06-30", "summarize_column_by": "Month"}),
    ("02_pnl_2026-01_to_06_monthly_cash", "get_profit_and_loss",
     {"start_date": "2026-01-01", "end_date": "2026-06-30", "summarize_column_by": "Month", "accounting_method": "Cash"}),
    ("03_pnl_default_no_params", "get_profit_and_loss", {}),
    ("04_gl_2026-01_to_04", "get_general_ledger",
     {"start_date": "2026-01-01", "end_date": "2026-04-30", "accounting_method": "Accrual"}),
    ("05_gl_2000-01_to_2026-04", "get_general_ledger",
     {"start_date": "2000-01-01", "end_date": "2026-04-30", "accounting_method": "Accrual"}),
    ("06_invoices_before_2026-05-01", "search_invoices",
     {"criteria": [{"field": "TxnDate", "value": "2026-05-01", "operator": "<"}]}),
    ("07_balance_sheet_2026-06-30", "get_balance_sheet",
     {"start_date": "2026-06-30", "end_date": "2026-06-30", "accounting_method": "Accrual"}),
    ("08_company_info", "get_company_info", {}),
]
CALLED_AT = "2026-10-12 (report Header.Time values 06:59:05-06:59:37 America/Los_Angeles)"

SECRET_KEYS = re.compile(r"(?i)^(realm_?id|company_?id|access_?token|refresh_?token|id_?token|client_?secret|"
                         r"client_?id|authorization|auth_?code|code|token|password|secret)$")
PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"),
    "bearer": re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    "url_with_credentials": re.compile(r"https?://[^/\s:@]+:[^@\s/]+@\S+"),
    "url_with_token_query": re.compile(r"https?://\S*[?&](?:code|token|access_token|realmId|state)=\S+", re.I),
    "realm_path": re.compile(r"/company/\d{6,}"),
    "long_numeric_id": re.compile(r"(?<![\d.])\d{12,20}(?![\d.])"),  # QBO realm IDs are 12-20 digits
}


def redact(node, log):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if SECRET_KEYS.match(k) and isinstance(v, (str, int)):
                log[f"key:{k}"] = log.get(f"key:{k}", 0) + 1
                out[k] = "[REDACTED]"
            else:
                out[k] = redact(v, log)
        return out
    if isinstance(node, list):
        return [redact(v, log) for v in node]
    if isinstance(node, str):
        for name, pat in PATTERNS.items():
            node, n = pat.subn(f"[REDACTED:{name}]", node)
            if n:
                log[name] = log.get(name, 0) + n
        return node
    return node


def residual(text):
    return [name for name, pat in PATTERNS.items() if pat.search(text)]


def money(v):
    return float(v) if v not in ("", None) else 0.0


def walk_rows(rows):
    for r in rows.get("Row", []):
        for part in ("Header", "Summary"):
            if part in r:
                yield r[part]["ColData"]
        if "ColData" in r:
            yield r["ColData"]
        if "Rows" in r:
            yield from walk_rows(r["Rows"])


def find(report, label):
    return next(c for c in walk_rows(report["Rows"]) if c[0]["value"] == label)


def checks(responses):
    acc, cash = responses["01_pnl_2026-01_to_06_monthly_accrual"], responses["02_pnl_2026-01_to_06_monthly_cash"]
    bs = responses["07_balance_sheet_2026-06-30"]
    months = [c["ColTitle"] for c in acc["Columns"]["Column"][1:-1]]
    results = []

    def add(claim, ok, detail):
        results.append({"claim": claim, "passed": bool(ok), "detail": detail})

    add("Monthly P&L returns all six months Jan-Jun 2026 as columns (request parameters are correct)",
        months == ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026"], months)
    for name, rep in (("accrual", acc), ("cash", cash)):
        bad = []
        for cols in walk_rows(rep["Rows"]):
            vals = [money(c["value"]) for c in cols[1:]]
            if abs(sum(vals[:-1]) - vals[-1]) > 0.005:
                bad.append(cols[0]["value"])
        add(f"Every {name} P&L row: months sum to Total (transcription integrity)", not bad, bad or "all rows")
    ni = [money(c["value"]) for c in find(acc, "Net Income")[1:]]
    inc = [money(c["value"]) for c in find(acc, "Total Income")[1:]]
    add("Accrual: Jan-Apr 2026 are zero on every line; activity only in May and Jun",
        all(money(c["value"]) == 0 for cols in walk_rows(acc["Rows"]) for c in cols[1:5]),
        {"Total Income": dict(zip(months + ["Total"], inc)), "Net Income": dict(zip(months + ["Total"], ni))})
    cash_inc = [money(c["value"]) for c in find(cash, "Total Income")[1:]]
    add("Cash basis: only June has activity (May accrual income 391.25 was not yet received in cash)",
        cash_inc[:5] == [0.0] * 5 and cash_inc[5] == 391.25, dict(zip(months + ["Total"], cash_inc)))
    for key in ("04_gl_2026-01_to_04", "05_gl_2000-01_to_2026-04"):
        opt = {o["Name"]: o["Value"] for o in responses[key]["Header"]["Option"]}
        add(f"General ledger {responses[key]['Header']['StartPeriod']}..{responses[key]['Header']['EndPeriod']} has no transactions",
            opt.get("NoReportData") == "true" and not responses[key]["Rows"], opt)
    add("No invoices dated before 2026-05-01", responses["06_invoices_before_2026-05-01"].strip() == "Found 0 invoices",
        responses["06_invoices_before_2026-05-01"].strip())
    default = responses["03_pnl_default_no_params"]["Header"]
    add("With no parameters the tool defaults to 'this calendar year-to-date', one Total column",
        default.get("DateMacro") == "this calendar year-to-date" and default.get("SummarizeColumnsBy") == "Total",
        {k: default.get(k) for k in ("DateMacro", "StartPeriod", "EndPeriod", "SummarizeColumnsBy")})
    company = responses["08_company_info"]
    add("Sandbox company was created 2026-10-10 (sample data is generated relative to this date)",
        company["CompanyStartDate"] == "2026-10-10", {"CompanyStartDate": company["CompanyStartDate"],
                                                    "CreateTime": company["MetaData"]["CreateTime"]})
    total = lambda label: money(find(bs, label)[1]["value"])
    assets, liab, equity = total("TOTAL ASSETS"), total("Total Liabilities"), total("Total Equity")
    add("Balance Sheet 2026-06-30: assets = liabilities + equity", abs(assets - liab - equity) <= 0.005,
        {"assets": assets, "liabilities": liab, "equity": equity})
    bs_ni = money(find(bs, "Net Income")[1]["value"])
    add("Balance Sheet net income (456.25) ties to P&L Jan-Jun 2026 accrual net income total",
        abs(bs_ni - ni[-1]) <= 0.005, {"balance_sheet": bs_ni, "pnl_total": ni[-1]})
    return results


def main():
    raw = Path(sys.argv[1])
    log, responses = {}, {}
    for name, tool, params in CALLS:
        src = next(raw.glob(f"{name}.response.*"))
        (HERE / f"{name}.request.json").write_text(json.dumps(
            {"server": SERVER, "tool": tool, "params": params, "called_at": CALLED_AT}, indent=2) + "\n", encoding="utf-8")
        file_log = {}
        if src.suffix == ".json":
            data = json.loads(src.read_text(encoding="utf-8"))
            responses[name] = data
            text = json.dumps(redact(data, file_log), indent=2) + "\n"
            out = HERE / f"{name}.response.redacted.json"
        else:
            responses[name] = src.read_text(encoding="utf-8")
            text = redact(responses[name], file_log)
            out = HERE / f"{name}.response.redacted.txt"
        left = residual(text)
        if left:
            raise SystemExit(f"{out.name}: secret-like patterns survived redaction: {left}")
        out.write_text(text, encoding="utf-8")
        log[out.name] = file_log or "nothing to redact"
    (HERE / "redaction_log.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    results = checks(responses)
    (HERE / "checks.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for r in results:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['claim']}")
    print("redactions:", json.dumps(log))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
