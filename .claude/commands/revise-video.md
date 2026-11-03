---
description: Revise a video production package.
allowed-tools: Bash, Read, Edit
argument-hint: <video id> <what to change>
---

Revise the video package: $ARGUMENTS

1. Read `outputs/videos/<video_id>/package.json` and its evidence packet.
2. Make the requested change in `package.json` (the other files in the folder are regenerated from it). Any new factual line needs a claim id from the packet; if the fact is not in the packet, say so and do not add it.
3. Keep runtime, voiceover pace, hedging and the AI-generated disclosure valid.
4. Run `python scripts/make_video.py check <video_id>` and fix every ERROR. Use `.venv/bin/python` if `python` is not on PATH.
5. Tell the editor what changed and show the affected sections.
