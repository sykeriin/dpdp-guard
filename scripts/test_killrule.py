import csv, importlib.util, pathlib
from datetime import date
spec = importlib.util.spec_from_file_location("killrule", pathlib.Path(__file__).parent / "killrule.py")
k = importlib.util.module_from_spec(spec); spec.loader.exec_module(k)

def rows(n_yes, n_no, n_maybe=0, pilots=0):
    out = [{"name": f"y{i}", "would_pay": "Y", "price_inr_month": "3000", "competitor_named": "Periskope;Boei", "pilot": "Y" if i < pilots else "N"} for i in range(n_yes)]
    out += [{"name": f"n{i}", "would_pay": "N"} for i in range(n_no)] + [{"name": f"m{i}", "would_pay": "MAYBE"} for i in range(n_maybe)]
    return out

def test_pass_when_eight_yes():
    assert k.evaluate(rows(8, 5), date(2026, 11, 10))["rule1"].startswith("PASS")

def test_maybe_does_not_count_and_pending_counts_remaining():
    e = k.evaluate(rows(5, 3, n_maybe=4), date(2026, 11, 10))      # 12 calls, 5 yes, 8 left
    assert e["yes"] == 5 and e["maybe"] == 4 and e["rule1"].startswith("PENDING") and "3 more yes" in e["rule1"]

def test_fails_early_when_mathematically_unreachable():
    assert k.evaluate(rows(2, 16), date(2026, 11, 8))["rule1"].startswith("FAIL: only 2 yes")   # 18 calls, 2 left: max 4

def test_fails_after_deadline_with_too_few():
    assert k.evaluate(rows(6, 4), date(2026, 11, 16))["rule1"].startswith("FAIL: deadline passed")

def test_pilot_rule_and_competitor_ranking():
    e = k.evaluate(rows(8, 2, pilots=3), date(2027, 1, 10))
    assert e["rule2"].startswith("PASS") and e["competitors"][0] == ("Periskope", 8) and e["median_price"] == 3000

def test_csv_loader_ignores_example_rows(tmp_path):
    p = tmp_path / "i.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "would_pay"]); w.writeheader()
        w.writerow({"name": "EXAMPLE person", "would_pay": "Y"}); w.writerow({"name": "Real One", "would_pay": "Y"})
    assert len(k.load(str(p))) == 1

def test_template_csv_has_only_the_example_row():
    assert k.load(str(pathlib.Path(__file__).parent.parent / "docs" / "interviews.csv")) == []

def test_cli_end_to_end(tmp_path, capsys):
    p = tmp_path / "i.csv"
    p.write_text("name,would_pay,price_inr_month,competitor_named,pilot\n" + "".join(f"p{i},Y,2000,Boei,N\n" for i in range(3)) + "q,N,,,N\n")
    rc = k.main([str(p), "--today", "2026-11-05"])
    out = capsys.readouterr().out
    assert rc == 0 and "calls: 4/20" in out and "would-pay YES: 3" in out and "PENDING: need 5 more yes" in out
    assert k.main([str(p), "--today", "2026-11-20"]) == 1          # deadline passed with 3/8 -> non-zero exit
