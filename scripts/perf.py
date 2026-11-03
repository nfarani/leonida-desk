#!/usr/bin/env python3
"""Video performance log and the operator's calibration ratings. Measured numbers only.

  python scripts/perf.py log <video_id> <platform> --checkpoint 1h|24h|7d|latest --views N [--likes N]
        [--comments N] [--shares N] [--watch-time-s N] [--avg-pct-viewed N] [--completion-rate N] [--followers N]
  python scripts/perf.py show                      # every post with its numbers
  python scripts/perf.py review                    # the 10-video review (says so when there is too little data)
  python scripts/perf.py rate <story id> GREAT|GOOD|MEDIOCRE|BAD [--note "..."]
  python scripts/perf.py calibration               # operator ratings against the system's scores
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

import _path  # noqa: F401
from research import db
from research.config import load_config, resolve

REVIEW_AT = 10
RATINGS = ["GREAT", "GOOD", "MEDIOCRE", "BAD"]
SCORES = ["opportunity", "viral", "significance", "momentum", "recommendation_confidence"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cmd_log(conn, a):
    post = conn.execute("SELECT id FROM video_posts WHERE video_id=? AND platform=?", (a.video_id, a.platform)).fetchone()
    if not post:
        sys.exit("No such post. Log the post first: python scripts/make_video.py publish <video_id> --platform ... --url ...")
    conn.execute("""INSERT OR REPLACE INTO video_metrics(post_id, checkpoint, captured_at, views, likes, comments, shares,
                    watch_time_s, avg_pct_viewed, completion_rate, followers_gained) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (post["id"], a.checkpoint, now(), a.views, a.likes, a.comments, a.shares, a.watch_time_s,
                  a.avg_pct_viewed, a.completion_rate, a.followers))
    conn.commit()
    print(f"Logged {a.checkpoint} numbers for {a.video_id} on {a.platform}.")


def _posts(conn):
    posts = [dict(r) for r in conn.execute("SELECT * FROM video_posts ORDER BY published_at")]
    for p in posts:
        p["metrics"] = {m["checkpoint"]: dict(m) for m in conn.execute("SELECT * FROM video_metrics WHERE post_id=?", (p["id"],))}
    return posts


def _best(p):
    """The most mature measurement a post has."""
    return next((p["metrics"][c] for c in ("7d", "latest", "24h", "1h") if c in p["metrics"]), None)


def cmd_show(conn, a):
    posts = _posts(conn)
    if not posts:
        print("No videos have been logged as published yet.")
    for p in posts:
        print(f"{p['published_at'][:16]} {p['platform']:15} {p['video_id']}\n    {p['game'] or 'General'} · {p['treatment']} · "
              f"hook {p['hook_style']} · {p['seconds']:.0f}s · {p['visual_style'] or 'no visual style noted'} · {p['url'] or 'no url'}")
        for c in ("1h", "24h", "7d", "latest"):
            m = p["metrics"].get(c)
            if m:
                print(f"    {c:6} views {m['views']} · likes {m['likes']} · comments {m['comments']} · shares {m['shares']} · "
                      f"avg viewed {m['avg_pct_viewed']}% · completion {m['completion_rate']}% · followers +{m['followers_gained']}")
        if not p["metrics"]:
            print("    no numbers logged yet")


def cmd_review(conn, a):
    posts = _posts(conn)
    videos = {p["video_id"] for p in posts}
    measured = [p for p in posts if _best(p) and _best(p)["views"] is not None]
    print(f"Published videos: {len(videos)} · posts: {len(posts)} · posts with numbers: {len(measured)}\n")
    if len(videos) < REVIEW_AT:
        print(f"The first review is due after {REVIEW_AT} published videos. With {len(videos)}, any pattern below is noise: "
              "do not draw strategic conclusions from it.\n")
    if not measured:
        print("No measured numbers yet, so there is nothing to compare.")
        return

    def table(title, key):
        groups = defaultdict(list)
        for p in measured:
            groups[key(p) or "not recorded"].append(_best(p))
        print(title)
        for name, ms in sorted(groups.items(), key=lambda kv: -sum(m["views"] for m in kv[1]) / len(kv[1])):
            pct = [m["avg_pct_viewed"] for m in ms if m["avg_pct_viewed"] is not None]
            print(f"  {name:28} n={len(ms):<2} avg views {sum(m['views'] for m in ms) / len(ms):>9.0f} · avg % viewed "
                  + (f"{sum(pct) / len(pct):.0f}" if pct else "not logged"))
        print()

    table("By game", lambda p: p["game"])
    table("By topic", lambda p: p["topic"])
    table("By hook style", lambda p: p["hook_style"])
    table("By treatment", lambda p: p["treatment"])
    table("By visual style", lambda p: p["visual_style"])
    table("By length", lambda p: "under 30s" if p["seconds"] < 30 else "30-37s" if p["seconds"] < 38 else "38-45s")
    ranked = sorted(measured, key=lambda p: -_best(p)["views"])
    print("Best:  " + "; ".join(f"{p['video_id']} on {p['platform']} ({_best(p)['views']} views)" for p in ranked[:3]))
    print("Worst: " + "; ".join(f"{p['video_id']} on {p['platform']} ({_best(p)['views']} views)" for p in ranked[-3:]))
    print("\nGroups with n=1 or n=2 say nothing on their own. 'Make more of' and 'stop making' are the editor's call "
          "from this table, not a computed verdict.")


def cmd_rate(conn, a):
    r = conn.execute("SELECT headline, opportunity_score, viral_score, score_breakdown, desk FROM stories WHERE id=?",
                     (a.story_id,)).fetchone()
    if not r:
        sys.exit(f"No story #{a.story_id}.")
    d = json.loads(r["desk"] or "{}")
    dims = json.loads(r["score_breakdown"] or "{}")
    dims = dims.get("dims", dims) if isinstance(dims, dict) else {}
    sig = dims.get("significance")
    scores = {"opportunity": r["opportunity_score"], "viral": r["viral_score"],
              "significance": round(100 * sig, 1) if isinstance(sig, (int, float)) else None,
              "momentum": d.get("momentum"), "recommendation_confidence": d.get("recommendation_confidence"),
              "hot_rank": d.get("desk_rank")}
    conn.execute("INSERT INTO story_ratings(story_id, rating, note, scores, rated_at) VALUES (?,?,?,?,?)",
                 (a.story_id, a.rating.upper(), a.note, json.dumps(scores), now()))
    conn.commit()
    print(f"Rated #{a.story_id} {a.rating.upper()}: {r['headline'][:80]}\n  system: {scores}")


def cmd_calibration(conn, a):
    rows = [(r["rating"], json.loads(r["scores"])) for r in conn.execute("SELECT rating, scores FROM story_ratings")]
    print(f"Operator ratings: {len(rows)}\n")
    if not rows:
        print("No ratings yet. Rate candidates with: python scripts/perf.py rate <story id> GREAT|GOOD|MEDIOCRE|BAD")
        return
    print(f"{'rating':10} {'n':>3}  " + "  ".join(f"{s[:12]:>12}" for s in SCORES) + "   on the hot list")
    for rating in RATINGS:
        got = [s for r, s in rows if r == rating]
        if not got:
            continue
        avg = lambda k: (lambda v: f"{sum(v) / len(v):>12.0f}" if v else f"{'-':>12}")([s[k] for s in got if s.get(k) is not None])
        tiers = defaultdict(int)
        for s in got:
            tiers["listed" if s.get("hot_rank") else "not listed"] += 1
        print(f"{rating:10} {len(got):>3}  " + "  ".join(avg(k) for k in SCORES) + "   " + ", ".join(f"{k} {v}" for k, v in tiers.items()))
    wrong = [(r, s) for r, s in rows if (r in ("GREAT", "GOOD")) != bool(s.get("hot_rank"))]
    print(f"\nDisagreements (rated GREAT/GOOD but not on the hot list, or the reverse): {len(wrong)} of {len(rows)}")
    if len(rows) < 30:
        print(f"{len(rows)} ratings is too few to change a weight or threshold. Keep rating; this is evidence, not an instruction.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("log"); p.add_argument("video_id")
    p.add_argument("platform", choices=["youtube_shorts", "tiktok", "instagram", "youtube", "other"])
    p.add_argument("--checkpoint", required=True, choices=["1h", "24h", "7d", "latest"])
    p.add_argument("--views", type=int, required=True)
    for name in ("likes", "comments", "shares", "followers"):
        p.add_argument(f"--{name}", type=int)
    for name in ("watch-time-s", "avg-pct-viewed", "completion-rate"):
        p.add_argument(f"--{name}", type=float)
    for name in ("show", "review", "calibration"):
        sub.add_parser(name)
    p = sub.add_parser("rate"); p.add_argument("story_id", type=int); p.add_argument("rating", type=str.upper, choices=RATINGS)
    p.add_argument("--note")
    args = ap.parse_args()
    cfg = load_config()
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    globals()[f"cmd_{args.cmd}"](conn, args)


if __name__ == "__main__":
    main()
