#!/usr/bin/env python3
"""Measure rules-only vs rules+LLM intent accuracy on a labelled TSV (label<TAB>text; label 'none' = no rights intent).
Needs a real Anthropic credential: ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN). Refuses to run without one: no numbers are invented.
Cost: only rule MISSES go to the model (claude-haiku-5-5, $0.10/$0.50 per MTok at <=100K prompts), so ~100 calls cost well under $0.01.
Usage: python scripts/eval_llm_intent.py [sdk-python/tests/intent_heldout2.tsv] [--model claude-haiku-5-5] [--out result.json]
NOTE: intent_heldout.tsv and intent_eval.tsv were tuned on; only heldout2 (or a NEW set of real chat phrasings) is meaningful."""
import argparse
import collections
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sdk-python"))
from dpdp_guard import intent  # noqa: E402

PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6


class Metered:
    """Wraps a client and sums token usage so the report can state real cost."""
    def __init__(self, client): self.c, self.calls, self.tin, self.tout = client, 0, 0, 0
    @property
    def messages(self): return self
    def create(self, **kw):
        r = self.c.messages.create(**kw)
        self.calls += 1
        u = getattr(r, "usage", None)
        self.tin += getattr(u, "input_tokens", 0) or 0; self.tout += getattr(u, "output_tokens", 0) or 0
        return r


def load(path):
    rows = [l.rstrip("\n").split("\t", 1) for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return [(None if a == "none" else a, t) for a, t in rows]


def evaluate(rows, client, model="claude-haiku-5-5"):
    m = Metered(client)
    rules, comb = [], []
    for exp, text in rows:
        r = intent.classify_rules(text)
        rules.append(r)
        comb.append(r if r else intent.classify_llm(text, client=m, model=model))
    def score(preds):
        wrong = [(e, p, t) for (e, t), p in zip(rows, preds) if e != p]
        fp = [w for w in wrong if w[0] is None]                      # benign message wrongly given a rights intent
        wrong_label = [w for w in wrong if w[0] is not None and w[1] is not None]   # real request, WRONG intent
        silent = [w for w in wrong if w[0] is not None and w[1] is None]            # real request, no intent at all
        pos = sum(1 for e, _ in rows if e)
        return {"n": len(rows), "accuracy": round(1 - len(wrong) / len(rows), 3), "recall_any_intent": round(1 - len(silent) / max(pos, 1), 3),
                "false_positives": len(fp), "wrong_intent": len(wrong_label), "silent_misses": len(silent),
                "silent_examples": [w[2] for w in silent][:10], "fp_examples": [w[2] for w in fp][:10]}
    return {"rules_only": score(rules), "rules_plus_llm": score(comb), "llm_calls": m.calls, "input_tokens": m.tin, "output_tokens": m.tout,
            "cost_usd": round(m.tin * PRICE_IN + m.tout * PRICE_OUT, 6), "model": model}


def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument("tsv", nargs="?", default=str(ROOT / "sdk-python/tests/intent_heldout2.tsv"))
    ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("No ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN set. Not running: this script never fabricates a result.\n"
              "Add the key as a secret in the environment settings, start a new session, and rerun.", file=sys.stderr)
        return 2
    import anthropic
    res = evaluate(load(a.tsv), anthropic.Anthropic(), a.model)
    res["file"] = pathlib.Path(a.tsv).name
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if a.out: pathlib.Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
