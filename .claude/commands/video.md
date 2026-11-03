---
description: Inspect one video production package.
allowed-tools: Bash, Read
argument-hint: <video id>
---

Run `python scripts/make_video.py check $ARGUMENTS` and then read `outputs/videos/$ARGUMENTS/package.md` and `brief.md`. Present the package, its status, why the story was chosen (the gate checks in the brief), and any errors or warnings from the check. Use `.venv/bin/python` if `python` is not on PATH.
