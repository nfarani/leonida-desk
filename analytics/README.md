# analytics/ (milestone 5, not built yet)

Will hold the ANALYSE → LEARN stages:

- importers that fill `performance_metrics` from YouTube / TikTok / Instagram
- reports joining `recommendations` → `published_content` → `performance_metrics`
- calibration: compare judged-dimension scores against real outcomes and propose weight changes to
  `config/scoring.yaml` (proposals only; the operator approves changes)

The schema tables already exist so data captured from day one is usable later.
Log every published piece now with `scripts/mark_used.py`, even before analytics exists.
