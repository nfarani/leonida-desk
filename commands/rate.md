---
description: Record the editor's own rating of a candidate story, for scoring calibration.
allowed-tools: Bash
argument-hint: <story id> GREAT|GOOD|MEDIOCRE|BAD [note] | report
---

Calibration: $ARGUMENTS. Use `.venv/bin/python` if `python` is not on PATH.

- To rate: `python scripts/perf.py rate <story id> <GREAT|GOOD|MEDIOCRE|BAD> --note "<why>"`. The system's scores at that moment are stored with the rating.
- `report`: `python scripts/perf.py calibration` compares the ratings with opportunity, viral, significance, momentum, recommendation confidence and whether the story made the hot list.

Report what it prints. Do not change a scoring weight or a threshold from this data: that is the operator's decision, and not before there are enough ratings to mean something.
