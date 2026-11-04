# Free "audit one of your bots" offer: teardown template

How: the person sends (or screen-shares) a real conversation or flow. Paste it into the dashboard Bot checker (`/checker`) yourself, with their permission, before the call. Nothing is stored by the checker.

## What to send back (1 page)
**Bot:** {name} (reviewed {date}). **Score:** {n}/100 (heuristic, not a legal opinion).

| Finding | Where it appears | Why it matters (DPDP) | Fix |
|---|---|---|---|
| {title from checker} | {quote the line, mask any personal data} | {rule from the checker's explanation} | {fix from the checker} |

**What the checker can't see:** storage locations (CRM, vector DB, sheets), who can read transcripts, retention, breach process, children. Ask about each.

**Next step (only if they want it):** a 30-minute call to walk through the findings. If they ask what to pay for, that's a pricing data point for `docs/interviews.csv`; record it, don't quote a price you haven't validated.

## Ground rules
- Get explicit permission before running anyone's transcript, and never publish or share it. If it contains real customers' data, ask them to mask it first.
- Never name the client of the bot in any post.
- It is tooling output, not legal advice: say so on the page.
