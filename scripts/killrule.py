#!/usr/bin/env python3
"""Kill-rule tracker from the report. Reads docs/interviews.csv.
  Rule 1: by 15 Nov 2026, fewer than 8 of 20 interviewed bot builders say they would pay -> stop.
  Rule 2: by 15 Jan 2027, fewer than 3 paying pilots -> stop.
Only would_pay == Y counts (MAYBE does not). Rows whose name contains 'EXAMPLE' are ignored.
Usage: python scripts/killrule.py [csv] [--today YYYY-MM-DD]"""
import csv
import statistics
import sys
from collections import Counter
from datetime import date

R1_DEADLINE, R1_TARGET, R1_SAMPLE = date(2026, 11, 15), 8, 20
R2_DEADLINE, R2_TARGET = date(2027, 1, 15), 3


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if "EXAMPLE" not in (r.get("name") or "").upper() and (r.get("name") or "").strip()]


def evaluate(rows, today):
    n = len(rows)
    yes = sum(1 for r in rows if (r.get("would_pay") or "").strip().upper() == "Y")
    maybe = sum(1 for r in rows if (r.get("would_pay") or "").strip().upper() == "MAYBE")
    pilots = sum(1 for r in rows if (r.get("pilot") or "").strip().upper() == "Y")
    lois = sum(1 for r in rows if (r.get("loi") or "").strip().upper() == "Y")
    prices = [float(r["price_inr_month"]) for r in rows if (r.get("price_inr_month") or "").strip().replace(".", "", 1).isdigit()]
    comps = Counter(c.strip() for r in rows for c in (r.get("competitor_named") or "").split(";") if c.strip())

    remaining = max(R1_SAMPLE - n, 0)
    if yes >= R1_TARGET:
        r1 = "PASS (target reached)"
    elif yes + remaining < R1_TARGET:
        r1 = f"FAIL: only {yes} yes and {remaining} calls left, 8 is unreachable. Stop per the kill rule."
    elif today > R1_DEADLINE:
        r1 = f"FAIL: deadline passed with {yes}/{R1_TARGET} yes ({n} calls)."
    else:
        r1 = f"PENDING: need {R1_TARGET - yes} more yes from at most {remaining} more calls ({(R1_DEADLINE - today).days} days left)."
    if pilots >= R2_TARGET:
        r2 = "PASS (target reached)"
    elif today > R2_DEADLINE:
        r2 = f"FAIL: deadline passed with {pilots}/{R2_TARGET} paying pilots."
    else:
        r2 = f"PENDING: {pilots}/{R2_TARGET} paying pilots ({(R2_DEADLINE - today).days} days left)."
    return {"calls": n, "yes": yes, "maybe": maybe, "lois": lois, "pilots": pilots,
            "median_price": statistics.median(prices) if prices else None, "competitors": comps.most_common(), "rule1": r1, "rule2": r2}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Kill-rule tracker")
    ap.add_argument("csv", nargs="?", default="docs/interviews.csv")
    ap.add_argument("--today", type=date.fromisoformat, default=None, help="override today's date (YYYY-MM-DD)")
    a = ap.parse_args(argv)
    path, today = a.csv, a.today or date.today()
    e = evaluate(load(path), today)
    print(f"calls: {e['calls']}/20   would-pay YES: {e['yes']} (+{e['maybe']} maybe, not counted)   LOIs: {e['lois']}   paying pilots: {e['pilots']}")
    print(f"median quoted price: {e['median_price'] if e['median_price'] is not None else 'n/a'} INR/month")
    print("competitors named: " + (", ".join(f"{c} x{k}" for c, k in e["competitors"]) or "none yet"))
    if e["competitors"] and e["competitors"][0][1] >= 3:
        print(f"  ! {e['competitors'][0][0]} named {e['competitors'][0][1]} times: the report says to adjust positioning or drop the idea if one tool keeps coming up")
    print("Rule 1 (by 15 Nov):", e["rule1"]); print("Rule 2 (by 15 Jan):", e["rule2"])
    return 1 if e["rule1"].startswith("FAIL") or e["rule2"].startswith("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
