---
description: List video packages, their production status and progress on the 10-video sprint.
allowed-tools: Bash
---

Run `python scripts/make_video.py list` and present it as a table: status, label, runtime, video id, title, then the sprint count. Use `.venv/bin/python` if `python` is not on PATH.
Statuses: IDEA → SCRIPTED (has errors) → READY_FOR_GENERATION → GENERATING → READY_FOR_REVIEW → APPROVED → PUBLISHED, or REJECTED.
