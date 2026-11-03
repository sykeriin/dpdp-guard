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
