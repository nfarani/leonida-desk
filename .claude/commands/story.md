---
description: Full intelligence for one story.
allowed-tools: Bash, Read
argument-hint: <story id>
---

Run `python scripts/desk.py story $ARGUMENTS` and present it: label, scores, every source with tier and date, the last recommendation, and any evidence packet, article or video already made from it. Use `.venv/bin/python` if `python` is not on PATH.
Do not add facts that are not in the output. If the story was merged, give the id it was merged into.
