"""Run the monthly analysis for one client, driven entirely by clients/<client>/config.yaml.

    python src/run_client.py abc
    python src/run_client.py xyz

Outputs go to outputs/<client>/ (outputs/ is next to this project folder). The run is sandboxed:
it cannot read another client's folder or outputs, and cannot write anywhere except outputs/<client>/.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import abc_workbook_adapter as engine  # noqa: E402
import excel_layout  # noqa: E402
from client_sandbox import client_sandbox  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
CLIENTS_ROOT = PROJECT / "clients"
OUTPUTS_ROOT = PROJECT.parent / "outputs"
CLIENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
REQUIRED = {
    "client": str, "display_name": str, "workbook": str, "sheets": dict, "layout": dict,
    "sections": dict, "totals": dict, "subtotal_rows": list, "categories": list,
    "account_to_category": dict, "fiscal_year": dict,
}


def load_config(client: str, clients_root: Path = CLIENTS_ROOT) -> dict:
    """Read and validate a client config. Must be called inside that client's sandbox."""
    if not CLIENT_ID.match(client):
        raise ValueError(f"Invalid client id {client!r}; use lowercase letters, digits, '-' or '_'.")
    path = Path(clients_root) / client / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in cfg]
    wrong = [k for k, t in REQUIRED.items() if k in cfg and not isinstance(cfg[k], t)]
    if missing or wrong:
        raise ValueError(f"{path}: missing keys {missing}, wrong types {wrong}")
    if cfg["client"] != client:
        raise ValueError(f"{path}: client is {cfg['client']!r} but folder is {client!r}")
    if set(cfg["sections"]) != set(engine.SECTIONS):
        raise ValueError(f"{path}: sections must define exactly {list(engine.SECTIONS)}")
    if set(cfg["totals"]) != set(engine.ABC_TOTALS):
        raise ValueError(f"{path}: totals must define exactly {list(engine.ABC_TOTALS)}")
    bad = sorted({c for c in cfg["account_to_category"].values() if c not in cfg["categories"]})
    if bad:
        raise ValueError(f"{path}: account_to_category uses undeclared categories {bad}")
    start = cfg["fiscal_year"].get("start_month")
    if not isinstance(start, int) or not 1 <= start <= 12:
        raise ValueError(f"{path}: fiscal_year.start_month must be an integer 1-12")
    cfg["workbook_path"] = (path.parent / cfg["workbook"]).resolve()
    return cfg


def data_quality(cfg, account_month, monthly, expense_trends, rollup) -> list[str]:
    warnings = []
    opex_accounts = set(expense_trends["expense_category"])
    mapped = set(cfg["account_to_category"])
    for a in sorted(opex_accounts - mapped):
        warnings.append(f"Unmapped OPEX account (reported under 'Unmapped'): {a}")
    for a in sorted(mapped - opex_accounts):
        warnings.append(f"Mapped account not found in workbook OPEX section: {a}")
    present = set(rollup["category"])
    for c in cfg["categories"]:
        if c not in present:
            warnings.append(f"Missing category: no '{c}' accounts in the source; reported as not available, not zero.")
    sums = rollup.groupby("month")["amount"].sum()
    for m, total in monthly.set_index("month")["operating_expenses"].items():
        if abs(sums.get(m, 0) - total) > 0.005:
            warnings.append(f"Category rollup {sums.get(m, 0):,.2f} != total OPEX {total:,.2f} in {m:%b %Y}")
    months = pd.to_datetime(monthly["month"])
    if not ((months.dt.year * 12 + months.dt.month).diff().dropna() == 1).all():
        warnings.append("Months are not consecutive; TTM is withheld for windows with gaps.")
    if monthly["revenue_ttm"].isna().all():
        warnings.append(f"TTM not available: {len(monthly)} months supplied, 12 consecutive required.")
    return warnings


def run(client: str, clients_root: Path = CLIENTS_ROOT, outputs_root: Path = OUTPUTS_ROOT) -> dict:
    """Run one client's analysis inside its sandbox and return the written output paths."""
    with client_sandbox(client, clients_root, outputs_root):
        cfg = load_config(client, clients_root)
        layout = {
            "sheet": cfg["sheets"]["income_statement"],
            "header_label": cfg["layout"]["header_label"],
            "month_format": cfg["layout"]["month_format"],
            "sections": {sid: (v["header"], v["total"]) for sid, v in cfg["sections"].items()},
        }
        account_month = engine.parse_wide_income_statement(cfg["workbook_path"], layout)
        monthly = engine.build_monthly_summary(account_month, cfg["totals"])
        monthly = engine.add_fiscal_year(monthly, cfg["fiscal_year"]["start_month"])
        expense_trends = engine.build_expense_category_trends(account_month, cfg["subtotal_rows"])
        rollup = engine.build_category_rollup(expense_trends, cfg["account_to_category"])
        one_offs = engine.find_one_off_items(account_month)
        cash = None
        if cfg["sheets"].get("balance_sheet"):
            bs = engine.parse_wide_income_statement(cfg["workbook_path"], {**engine.ABC_BS_LAYOUT, "sheet": cfg["sheets"]["balance_sheet"]})
            cash = engine.cash_position(bs)
        commentary = engine.generate_commentary(monthly, account_month, cash)
        warnings = data_quality(cfg, account_month, monthly, expense_trends, rollup)

        out_dir = Path(outputs_root) / client
        out_dir.mkdir(parents=True, exist_ok=True)
        workbook_out = out_dir / "analysis.xlsx"
        sheets = {
            "Monthly Trends": monthly, "Expense Categories": rollup, "Expense Accounts": expense_trends,
            "Account Values": account_month.rename_axis("account").reset_index(), "One-off Items": one_offs,
            "Data Quality": pd.DataFrame({"warning": warnings or ["None"]}),
            "Commentary": pd.DataFrame({"commentary": commentary}),
        }
        with pd.ExcelWriter(workbook_out, engine="openpyxl") as writer:
            for name, frame in sheets.items():
                frame.dropna(axis=1, how="all").to_excel(writer, sheet_name=name, index=False)  # no all-blank columns
            for ws in writer.book.worksheets:
                excel_layout.polish_sheet(ws, wrap={"warning", "commentary"})
            excel_layout.drop_empty(writer.book)

        latest = monthly.iloc[-1]
        summary = {
            "client": client, "display_name": cfg["display_name"], "source": cfg["workbook"],
            "months": len(monthly), "period": f"{monthly['month'].iloc[0]:%b %Y} - {latest['month']:%b %Y}",
            "fiscal_year_start_month": cfg["fiscal_year"]["start_month"], "latest_fiscal_year": latest["fiscal_year"],
            "latest": {k: (None if pd.isna(latest[k]) else round(float(latest[k]), 6)) for k in monthly.columns
                       if k not in {"month", "fiscal_year"}},
            "categories_latest": {r.category: round(float(r.amount), 2)
                                  for r in rollup[rollup["month"] == latest["month"]].itertuples()},
            "warnings": warnings,
        }
        summary_out = out_dir / "summary.json"
        summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        commentary_out = out_dir / "commentary.md"
        commentary_out.write_text(
            f"# {cfg['display_name']} — {latest['month']:%b %Y}\n\n" + "\n".join(f"- {c}" for c in commentary)
            + "\n\n## Data quality\n\n" + "\n".join(f"- {w}" for w in warnings or ["None"]) + "\n", encoding="utf-8")
    return {"workbook": workbook_out, "summary": summary_out, "commentary": commentary_out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client", help="client id = folder name under clients/")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    paths = run(args.client)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    print(f"{summary['display_name']} ({args.client}): {summary['period']}, {summary['months']} months, "
          f"latest fiscal year {summary['latest_fiscal_year']}")
    for name, p in paths.items():
        print(f"  {name}: {p}")
    print(f"  warnings: {len(summary['warnings'])}")
    for w in summary["warnings"]:
        print(f"    - {w}")


if __name__ == "__main__":
    main()
