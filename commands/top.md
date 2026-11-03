---
description: The latest hot list, then the radar.
allowed-tools: Bash, Read
argument-hint: [how many]
---

Run `python scripts/desk.py top -n <N>` (N is the number given here, or 20 if none: $ARGUMENTS) and present the result as a table: rank, game, headline, type, label, hot score, opportunity, significance, freshness. Use `.venv/bin/python` if `python` is not on PATH. If the briefing is stale (the script says so), suggest `/morning`.
