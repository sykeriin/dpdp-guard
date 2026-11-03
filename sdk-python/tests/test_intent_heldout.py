"""Reports accuracy only (no assert: a threshold would invite tuning). heldout.tsv is BURNED (tuned on after first run, 58.9% first-run).
heldout2.tsv was written after that tuning; its FIRST-RUN number is the honest one. Held-out intent set. The rules were NOT tuned on these lines when first run (see README for first-run score).
If you tune rules on misses here, move those lines into intent_eval.tsv and write fresh held-out ones."""
import pathlib
from dpdp_guard import intent

import pytest

@pytest.mark.parametrize("fname", ["intent_heldout.tsv", "intent_heldout2.tsv"])
def test_heldout(fname, capsys):
    rows = [l.rstrip("\n").split("\t", 1) for l in (pathlib.Path(__file__).parent / fname).read_text(encoding="utf-8").splitlines() if l.strip()]
    data = [(a if a != "none" else None, b) for a, b in rows]
    wrong = [(e, intent.classify_rules(t), t) for e, t in data if intent.classify_rules(t) != e]
    fp = [w for w in wrong if w[0] is None]
    print(f"\nHELDOUT[{fname}] n={len(data)} accuracy={1 - len(wrong)/len(data):.3f} false_positives={len(fp)} misses={len(wrong)-len(fp)}")
    for w in wrong: print("MISS", w)
