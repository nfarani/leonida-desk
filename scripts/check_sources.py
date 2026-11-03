#!/usr/bin/env python3
"""Live-check every feed in config/sources.yaml. Use before flipping verified: true.

  python scripts/check_sources.py        # enabled feeds
  python scripts/check_sources.py --all  # include disabled
"""
import argparse
import re

import _path  # noqa: F401
from research.config import load_config
from research.discover.reddit import fetch_reddit
from research.discover.rss import fetch_rss

ap = argparse.ArgumentParser()
ap.add_argument("--all", action="store_true")
args = ap.parse_args()
cfg = load_config()
s = cfg["settings"]["discovery"]
pats = [re.compile(p, re.I) for p in cfg["settings"]["relevance"]["patterns"]]
for f in cfg["sources"]["feeds"]:
    if not args.all and not f.get("enabled", True):
        continue
    if "REPLACE_WITH" in f["url"]:
        print(f"⏭  {f['id']:<24} needs a real URL (see comment in sources.yaml)")
        continue
    items, err = (fetch_reddit if f["kind"] == "reddit" else fetch_rss)(f, s["user_agent"], s["request_timeout_seconds"])
    if err:
        print(f"✗  {f['id']:<24} {err}")
        continue
    rel = sum(1 for i in items if f.get("always_relevant") or any(p.search(i.title + " " + i.snippet) for p in pats))
    newest = max((i.published_at for i in items if i.published_at), default=None)
    print(f"✓  {f['id']:<24} {len(items):>3} items, {rel:>3} GTA-relevant, newest {newest}")
