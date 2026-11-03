#!/usr/bin/env python3
"""Record that the Editor-in-Chief turned a story into content (starts the 72h cooldown).

  python scripts/mark_used.py --rank 2 --platform tiktok --url https://...   # rank from latest run
  python scripts/mark_used.py --story-id 41 --platform youtube_shorts
  python scripts/mark_used.py --story-id 41 --reject                        # never recommend again
"""
import argparse

import _path  # noqa: F401
from research.config import load_config, resolve
from research.db import connect, mark_used

ap = argparse.ArgumentParser()
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--rank", type=int)
g.add_argument("--story-id", type=int)
ap.add_argument("--platform", choices=["youtube", "youtube_shorts", "tiktok", "instagram", "other"])
ap.add_argument("--url")
ap.add_argument("--title")
ap.add_argument("--format")
ap.add_argument("--reject", action="store_true")
a = ap.parse_args()

cfg = load_config()
conn = connect(resolve(cfg, cfg["settings"]["database_path"]))
rec_id = None
if a.rank:
    row = conn.execute("""SELECT r.id, r.story_id FROM recommendations r
                          WHERE r.run_id=(SELECT MAX(id) FROM runs WHERE finished_at IS NOT NULL) AND r.rank=?""",
                       (a.rank,)).fetchone()
    if not row:
        raise SystemExit("No such rank in the latest run.")
    rec_id, story_id = row["id"], row["story_id"]
else:
    story_id = a.story_id
headline = conn.execute("SELECT headline FROM stories WHERE id=?", (story_id,)).fetchone()
if not headline:
    raise SystemExit("Unknown story.")
if a.reject:
    conn.execute("UPDATE stories SET status='rejected' WHERE id=?", (story_id,))
    print(f"Rejected story #{story_id}: {headline[0]}")
else:
    if not a.platform:
        raise SystemExit("--platform is required unless --reject")
    mark_used(conn, story_id, a.platform, a.url, a.title, a.format, rec_id)
    print(f"Marked story #{story_id} as used on {a.platform}: {headline[0]}")
conn.commit()
