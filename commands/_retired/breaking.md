---
description: Only strong current developments from the latest briefing.
allowed-tools: Bash, Read
---

Run `python scripts/desk.py section breaking` and present the result as a compact list. Use `.venv/bin/python` if `python` is not on PATH.
If the section is empty, say so plainly: a quiet day is a valid result, and nothing is moved into BREAKING to fill it. If the briefing is more than six hours old, say so and suggest `/morning`.
