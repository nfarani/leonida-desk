#!/usr/bin/env python3
"""Run the full research pipeline and write a ranked editorial briefing.

  python scripts/morning.py                 # full run: the top 10 hot stories
  python scripts/morning.py --count 30      # the top 30 instead
  python scripts/morning.py --no-llm        # heuristics only, no API calls
  python scripts/morning.py --no-web-search # feeds only
"""
import argparse
import json

import _path  # noqa: F401
from research.config import load_config
from research.pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip Claude (editorial + adjudication + web search)")
    ap.add_argument("--no-web-search", action="store_true")
    ap.add_argument("--count", type=int, help="stories in the hot list (default: config, 10)")
    ap.add_argument("--fixture", help="JSON file of synthetic items (testing only)")
    args = ap.parse_args()
    cfg = load_config()
    if args.count:
        cfg["settings"]["ranking"]["hot_list"]["count"] = max(1, args.count)
    items = None
    if args.fixture:
        from research.fixtures import load_fixture
        items = load_fixture(args.fixture)
    path, recs = run(cfg, use_llm=not args.no_llm, use_web_search=not args.no_web_search, items_override=items)
    print(f"\nBriefing: {path}")
    for i, (s, p) in enumerate(recs, 1):
        print(f"{i:>2}. {'🚨' if p else '  '} {s.opportunity:5.1f}  [{s.verification_status}] {s.headline[:80]}")


if __name__ == "__main__":
    main()
