---
description: Source health: which feeds worked on the last run.
allowed-tools: Bash
---

Run `python scripts/desk.py sources` and present it. Use `.venv/bin/python` if `python` is not on PATH.
Call out failed feeds and feeds marked unverified. To re-test feeds live: `python scripts/check_sources.py`. Never add a feed that has not been seen returning items, and never invent an outlet.
