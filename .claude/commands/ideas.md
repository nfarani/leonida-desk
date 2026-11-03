---
description: Alternative editorial angles for one story.
allowed-tools: Bash, Read
argument-hint: <story id>
---

Propose alternative editorial angles for story $ARGUMENTS. Use `.venv/bin/python` if `python` is not on PATH.

1. Run `python scripts/desk.py story $ARGUMENTS` and read any evidence packet it lists in `data/evidence/`.
2. Offer three to five distinct angles. For each: the angle in one line, the best format (news brief, explainer, analysis, fact check, timeline), what it adds beyond the sources, and which stored sources or verified claims support it.
3. Use only what the stored sources say. An angle that needs a fact we do not have is listed separately as "needs evidence", with what would have to be found.
4. Angles on the same parent event must be substantively different (for example NPC systems, character writing, world research, satire), not rewordings of one another.

Do not draft anything. `/article` does that when the operator asks.
