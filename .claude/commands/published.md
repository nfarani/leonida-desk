---
description: Record that the editor posted a video, and log its performance numbers. Uploads nothing.
allowed-tools: Bash
argument-hint: <video id> <platform> <url> | <video id> <platform> <checkpoint> views=N ...
---

Record a published video or its numbers: $ARGUMENTS. Use `.venv/bin/python` if `python` is not on PATH.

- **A new post** (the video must be APPROVED): `python scripts/make_video.py publish <video_id> --platform youtube_shorts|tiktok|instagram --url <url>`. Run it once per platform. It logs the post, marks the package PUBLISHED, starts the story's 72-hour cooldown and reports progress on the 10-video sprint.
- **Numbers** (from the platform's own analytics, typed by the editor): `python scripts/perf.py log <video_id> <platform> --checkpoint 1h|24h|7d|latest --views N [--likes N --comments N --shares N --watch-time-s N --avg-pct-viewed N --completion-rate N --followers N]`.

Record only numbers the editor gives you. Never estimate, round up or fill a missing figure.
