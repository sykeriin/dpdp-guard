# Rights-intent classifier: measured accuracy (rules layer only)

| Set | n | Accuracy | Notes |
|---|---|---|---|
| `intent_eval.tsv` (tuning) | 158 | 100% | Rules were written against it. Not evidence of anything. |
| `intent_heldout.tsv` | 90 | **58.9% on first run** (35 misses, 1 false positive) | Then I rewrote the rules using these misses; now 100% and burned. |
| `intent_heldout2.tsv` | 69 | **73.9% on first run** (18 misses, 0 false positives) | Written after the rewrite and not tuned on. This is the number to quote. |

Reading it honestly:
- On unseen phrasings the regex layer catches roughly three quarters of rights requests. All 18 misses were "no action" (the message passes to the agent), never a wrong action. False positives were 1 in 159 negatives-and-positives across the first-run sets, and that one (an order-address edit read as a correction) is fixed and covered by a rule.
- Both held-out sets were written by the same person who wrote the rules, so real users will do worse. Collect real chat phrasings from pilots before quoting any figure to a customer.
- `Guard(use_llm=True)` sends rule misses to an LLM classifier. It is implemented but **not tested** (no API key in the dev environment), so its accuracy is unknown.
- A missed erasure/withdrawal request is a compliance failure, not just a UX one. Pilots should run with `use_llm=True` plus a human review of unclassified messages containing words like "data", "delete", "consent".

## Review queue (mitigation for the misses above)
Messages that mention data/deletion/consent/privacy but match no intent open a `review` ticket in the rights queue (`GuardResult.review_ref`) and still flow to the agent. Measured on `intent_heldout2.tsv`:
- 41 rights requests in the set; rules recognise 23 outright; the review queue catches 11 of the 18 misses; **7 (17%) are still silent** (e.g. "take me off your marketing list", "I moved, so the address in your file is outdated").
- 2 of 28 benign messages were flagged (noise a human skims).
- So "some handling" = 34/41 = 83% on a set the same author wrote. Real traffic will be worse. `use_llm=True` is the intended fix for the silent 17% but its accuracy is unmeasured (only its plumbing is tested, with a fake client).

## LLM fallback: how to measure it, and what it costs to run
- Harness: `python scripts/eval_llm_intent.py` (needs `ANTHROPIC_API_KEY`; exits 2 and prints nothing else without one). It reports rules-only vs rules+LLM accuracy, false positives, wrong-intent vs silent misses, tokens and dollar cost. **Not yet run: there was no key in the dev environment.**
- Production cost shape: with `use_llm=True` the model is called for **every message the rules don't match, i.e. almost every ordinary message**, not only rights requests. Each call is tiny (a short prompt, ~2 output tokens, thinking disabled, effort low), so cost is small at Haiku prices, but it adds a network round trip to every user turn and sends the raw message text to the model provider (a data-sharing fact your notice and contract must cover). If latency or data sharing matters, run the LLM only on messages that trip the review keywords (`_REVIEW`).
- Bug found while preparing this: the original fallback read `content[0].text`, but this model family can start a response with a thinking block, so the call would have failed silently and always returned "no intent". Fixed in `dpdp_guard/_llm.py` (thinking disabled, first *text* block read) and covered with tests, including one that serialises the request through the real SDK client.
