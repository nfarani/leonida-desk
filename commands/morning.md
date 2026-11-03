---
description: Daily hot list. The hottest GTA VI and gaming stories right now, scored and ranked. Optional: how many (default 10).
allowed-tools: Bash, Read, WebSearch, WebFetch, Task
argument-hint: [how many, default 10]
---

Produce today's Leonida Desk hot list. Follow CLAUDE.md strictly. Use `.venv/bin/python` if `python` is not on PATH.

N is the number given here ($ARGUMENTS), or 10 if none. N is a target, not a quota.

1. **Run the pipeline**
   `python scripts/morning.py --count N`
   If it errors, fix only what is necessary to run (missing deps, missing db), then rerun. Report what you fixed.

2. **Read** `outputs/briefings/latest.md`. The TOP N HOT STORIES section is the product; the rest is supporting detail. Note run warnings and failed feeds.

3. **Verify** (use the `verifier` agent): every POST NOW item and every story labelled CONFIRMED or HIGH_CONFIDENCE_REPORT in the top 10. Open the primary URL. Record OK/ISSUE per item. An item that fails verification leaves the list, and the next story on the radar does not move up unless it already qualifies.

4. **Freshness sweep** (use the `research-scout` agent): significant gaming developments from the last 24h that the pipeline missed, across gaming and not only GTA VI. Only URLs actually opened. Max 5. These are leads, not scored and not ranked.

5. **Present the hot list first** as a table: rank, game, story, type, label, hot score, opportunity, significance, freshness, momentum, saturation, published. Then, for each story, two or three lines: what happened, why it matters / why now, the primary source link, and the risk or caveat. Apply verifier corrections visibly.

6. If fewer than N stories qualify, say how many and why (stale, speculation, duplicates). If none qualify, say exactly: **NO HOT STORIES RIGHT NOW.** Never promote a story to fill a slot.

7. Then, briefly: the radar (the next stories down), further angles on capped topics, the pipeline's misses from the sweep, product and tech news in one line, and run health in one line.

8. End with the next commands: `/story <id>`, `/ideas <id>`, `/morning 20`.

Do not propose videos or articles; the operator asks for those. Never present a rumour as confirmed. Never invent a source.
