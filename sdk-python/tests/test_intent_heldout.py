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


def test_review_queue_coverage_of_rules_misses(capsys):
    """Of the rights requests the rules MISS in heldout2, how many still reach a human via the review queue?"""
    from dpdp_guard.guard import _REVIEW
    rows = [l.rstrip("\n").split("\t", 1) for l in (pathlib.Path(__file__).parent / "intent_heldout2.tsv").read_text(encoding="utf-8").splitlines() if l.strip()]
    missed = [t for e, t in rows if e != "none" and intent.classify_rules(t) is None]
    caught = [t for t in missed if _REVIEW.search(t)]
    benign_flagged = [t for e, t in rows if e == "none" and _REVIEW.search(t)]
    print(f"\nREVIEW COVERAGE: rules missed {len(missed)} rights requests; review queue catches {len(caught)} ({len(caught)/max(len(missed),1):.0%}); "
          f"benign messages flagged: {len(benign_flagged)}/{sum(1 for e,_ in rows if e=='none')}")
    for t in missed:
        if t not in caught: print("  STILL SILENT:", t)
