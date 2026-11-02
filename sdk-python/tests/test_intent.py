import collections, pathlib
from dpdp_guard import intent

def _load():
    rows = [l.rstrip("\n").split("\t", 1) for l in (pathlib.Path(__file__).parent / "intent_eval.tsv").read_text(encoding="utf-8").splitlines() if l.strip()]
    return [(a if a != "none" else None, b) for a, b in rows]

def test_eval_set_accuracy(capsys):
    data = _load()
    wrong = [(exp, got, t) for exp, t in data if (got := intent.classify_rules(t)) != exp]
    acc = 1 - len(wrong) / len(data)
    by = collections.Counter(e or "none" for e, _ in data)
    print(f"\nn={len(data)} accuracy={acc:.3f} classes={dict(by)}")
    for w in wrong: print("MISS", w)
    assert acc >= 0.95
    # false-positive guard: benign messages must never trigger a rights action
    assert not [w for w in wrong if w[0] is None]
