"""One-page owner memo in plain language, written from the review packet only (every number comes from the JSON).

Order: cash and runway first, then how the month went, then the questions for the owner. Describes what changed,
never why. It is graded by 03_evals/grade_commentary.py (grade_memo) when the sign-off pack is built.
"""
from __future__ import annotations

import re

import pandas as pd


def _usd(x):
    return f"${abs(x):,.0f}"


def _month(text):
    return f"{pd.Timestamp(text + '-01'):%b %Y}"


def _move(change):
    return f"{'up' if change >= 0 else 'down'} {_usd(change)}"


PLAIN = [(r"\bTTM\b", "twelve-month"), (r"\b(\d+)m\b", r"\1-month"), (r"\bMoM\b", "month-on-month"),
         (r"\bYoY\b", "year-on-year"), (r"\bopex\b", "operating costs"), (r"\bCOGS\b", "direct costs"),
         (r"\bYTD\b", "year to date")]


def plain(question):
    """Accountant shorthand in a question becomes plain words; the question itself is not changed."""
    for pattern, words in PLAIN:
        question = re.sub(pattern, words, question, flags=re.I)
    return question


def render(packet: dict, questions: list[str]) -> str:
    m, p = packet["latest_month"], packet["prior_month"]
    cur = packet["months"][m]
    name, month, prior = packet["display_name"], _month(m), _month(p)
    out = [f"# {name}: owner memo for {month}", "", "## Cash and runway", ""]
    cash = packet.get("cash")
    if cash:
        runway = cash["runway_months"].get(cash["primary_window"])
        out.append(f"You had {_usd(cash['value'])} in the bank at the end of {_month(cash['month'])}, "
                   f"{_usd(cash['mom_change'])} {'more' if cash['mom_change'] >= 0 else 'less'} than at the end of {prior}.")
        burn, n = cash["burn"].get(cash["primary_window"]), cash["primary_window"].rstrip("m")
        if runway is not None:
            out.append(f"Cash has been falling by about {_usd(burn)} a month over the last {n} months. "
                       f"At that pace you have about {runway:.1f} months of runway. "
                       "This looks only at past balances; it is not a forecast.")
        else:
            out.append(f"Cash did not fall over the last {cash['primary_window'].rstrip('m')} months, so the runway cannot be calculated.")
    else:
        out.append("No Balance Sheet cash is available for this client, so cash and runway are not shown.")
    out += ["", "## How the month went", ""]
    rev, gm, ni = cur["revenue"], cur["gross_profit"]["margin"], cur["net_income"]["value"]
    line = f"Revenue was {_usd(rev['value'])}, {_move(rev['mom_change'])} from {prior}"
    line += f" ({abs(rev['mom_pct']):.1%})." if rev.get("mom_pct") is not None else "."
    out.append(line)
    out.append(f"After the direct costs of delivering your service, you kept {gm:.1%} of revenue (gross margin).")
    out.append(f"The business {'made a profit' if ni >= 0 else 'made a loss'} of {_usd(ni)} for the month.")
    adj = packet.get("adjusted_net_income")
    if adj and adj["items"]:
        out.append(f"Leaving out the one-off items ({', '.join(adj['items'])}), the {'profit' if adj['adjusted_net_income'] >= 0 else 'loss'} "
                   f"would have been {_usd(adj['adjusted_net_income'])}.")
    elif adj:
        out.append("There were no one-off items this month, so the result above is unchanged.")
    yoy = packet.get("yoy", {})
    if yoy.get("available") and yoy["revenue"]["yoy_pct"] is not None:
        r = yoy["revenue"]
        out.append(f"Compared with {_month(yoy['prior_year_month'])}, revenue is {_move(r['yoy_change'])} ({abs(r['yoy_pct']):.1%}).")
    names = ", ".join(t["account"] for t in packet["top_movements"])
    out.append(f"The biggest changes from {prior} were in: {names}.")
    out += ["", "## Questions for you", ""]
    out += [f"- {plain(q)}" for q in questions] or ["- None this month."]
    return "\n".join(out) + "\n"
