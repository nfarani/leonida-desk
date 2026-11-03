#!/usr/bin/env python3
"""Read-only newsroom views behind /top, /story, /watchlist, /sources, /status and /analytics.
Nothing here fetches, writes or publishes.

  python scripts/desk.py top [-n 20]          # the hot list, then the radar
  python scripts/desk.py story <id>
  python scripts/desk.py watchlist
  python scripts/desk.py sources
  python scripts/desk.py status
  python scripts/desk.py analytics
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import _path  # noqa: F401
from research import articles as A
from research import db, games, video
from research.config import load_config, resolve


def latest(cfg):
    files = sorted(glob.glob(str(resolve(cfg, cfg["settings"]["briefings_dir"]) / "briefing_*.json")))
    if not files:
        sys.exit("No briefing yet. Run /morning first.")
    data = json.load(open(files[-1]))
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(data["generated_at"])).total_seconds() / 3600
    print(f"From the briefing generated {age:.1f}h ago" + ("  (stale: run /morning for a fresh one)" if age > 6 else "") + "\n")
    return data


def row(r, n=None):
    flag = "POST NOW " if r.get("post_now") else ""
    return (f"{n or r.get('rank', '-'):>2}. {flag}[{r.get('bucket', '')}] {r.get('game_name') or 'General'} · {r['headline'][:90]}\n"
            f"    {r['verification_status']} · hot {r['hot_score']:.0f} · opp {r['opportunity_score']:.0f} · "
            f"significance {100 * r['dims'].get('significance', 0):.0f} · freshness {r['freshness']:.2f} · "
            f"momentum {r.get('momentum', 0):.0f} · saturation {r['saturation_score']:.0f}\n"
            f"    why now: {r.get('why_now', '')}\n    angle: {r['editorial'].get('angle', '')}\n"
            f"    risk: {r['editorial'].get('risk', '')[:200]}\n    story #{r['story_id']}")


def cmd_top(cfg, args):
    data = latest(cfg)
    rows = (data["recommendations"] + data.get("radar", []))[: args.n]
    print("\n\n".join(row(r, n) for n, r in enumerate(rows, 1)) if rows else "Nothing on the latest hot list.")


def cmd_story(cfg, args):
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    stories = {s.id: s for s in db.load_recent_stories(conn, datetime.now(timezone.utc) - timedelta(days=3650))}
    s = stories.get(args.id)
    if not s:
        r = conn.execute("SELECT status, reasoning FROM stories WHERE id=?", (args.id,)).fetchone()
        sys.exit(f"Story #{args.id}: {r['reasoning']}" if r and r["reasoning"] else f"No story #{args.id}.")
    games.tag(s, cfg)
    r = conn.execute("SELECT * FROM stories WHERE id=?", (args.id,)).fetchone()
    print(f"#{s.id} {s.headline}\n{s.verification_status} · status {s.status} · game {s.desk.get('game_name') or 'General'} · "
          f"category {s.content_cluster} · parent event {s.desk.get('parent_event') or 'none detected'}")
    print(f"published {s.published_at} · first seen {s.first_seen_at} · last material update {s.last_material_update_at}")
    print(f"opportunity {r['opportunity_score']} · viral {r['viral_score']} · saturation {r['saturation_score']} · freshness {r['freshness_score']}")
    print(f"scores: {r['score_breakdown']}\nsummary: {s.summary}\nreasoning: {s.reasoning}\n\nSources ({len(s.items)}):")
    for i in sorted(s.items, key=lambda i: (i.tier, i.when)):
        print(f"  tier {i.tier} {i.source_type:10} {i.publisher[:18]:18} {str(i.published_at)[:16]}  {i.title[:70]}\n      {i.url}")
    last = conn.execute("""SELECT rank, post_now, editorial_bucket, recommended_output, recommended_angle, suggested_hook, risk_caveat
                           FROM recommendations WHERE story_id=? ORDER BY id DESC LIMIT 1""", (args.id,)).fetchone()
    if last:
        print(f"\nLast on the hot list: rank {last['rank']} · {last['editorial_bucket']}"
              f"{' · POST NOW' if last['post_now'] else ''}\n  angle: {last['recommended_angle']}\n  hook: {last['suggested_hook']}\n  risk: {last['risk_caveat']}")
    packets = [p.stem for p in sorted(A.evidence_dir(cfg).glob("*.json"))
               if args.id in (json.loads(p.read_text()).get("story_ids") or [])] if A.evidence_dir(cfg).exists() else []
    arts = [f"{m['slug']} ({m['status']})" for m, _, _ in A.all_articles(cfg) if m.get("story_id") == args.id]
    vids = [f"{p['video_id']} ({p['status']})" for p in video.all_packages(cfg) if p.get("story_id") == args.id]
    print(f"\nEvidence packets: {', '.join(packets) or 'none'}\nArticles: {', '.join(arts) or 'none'}\nVideos: {', '.join(vids) or 'none'}")


def cmd_watchlist(cfg, args):
    data = latest(cfg)
    rows = [r for r in data.get("skipped", []) if r.get("freshness", 0) >= 0.3]
    rows.sort(key=lambda r: -r["hot_score"])
    print("Emerging stories that are not on the hot list: fresh, but too weakly sourced to rank yet.\n")
    for r in rows[:15]:
        print(f"#{r['story_id']} [{r['verification_status']}] {r['headline'][:90]}\n    hot {r['hot_score']:.0f} · "
              f"freshness {r['freshness']:.2f} · skipped because: {r['reason']}")
    if not rows:
        print("Nothing on the watchlist.")
    for event, extra in data.get("angles", {}).items():
        print(f"\nFurther angles on {event}: " + "; ".join(f"#{x['story_id']} {x['headline'][:50]}" for x in extra[:5]))


def cmd_sources(cfg, args):
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    run = conn.execute("SELECT started_at, stats FROM runs WHERE stats IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    stats = json.loads(run["stats"]) if run else {}
    d = stats.get("discovery", {})
    failed = d.get("feeds_failed", {})
    print(f"Last run: {run['started_at'] if run else 'never'} · web search: {d.get('web_search')}\n")
    for f in cfg["sources"]["feeds"]:
        state = ("FAILED   " if f["id"] in failed else "ok       " if f["id"] in d.get("feeds_ok", []) else
                 "disabled " if not f.get("enabled", True) else "not run  ")
        print(f"{state} {f['id']:24} {f['source_type']:10} verified={str(f.get('verified', False)):5} {failed.get(f['id'], '')[:90]}")
    counts = conn.execute("""SELECT publisher, COUNT(*) n FROM story_sources WHERE fetched_at >= ?
                             GROUP BY publisher ORDER BY n DESC LIMIT 12""",
                          ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),)).fetchall()
    print("\nMost items in the last 48h: " + ", ".join(f"{r['publisher']} {r['n']}" for r in counts))


def cmd_status(cfg, args):
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    run = conn.execute("SELECT started_at, finished_at, stats FROM runs WHERE stats IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    stats = json.loads(run["stats"]) if run else {}
    d = stats.get("discovery", {})
    site = resolve(cfg, "site")
    arts, vids = {}, {}
    for m, _, _ in A.all_articles(cfg):
        arts[m.get("status")] = arts.get(m.get("status"), 0) + 1
    for p in video.all_packages(cfg):
        vids[p["status"]] = vids.get(p["status"], 0) + 1
    def env(k):
        return "set" if os.environ.get(k) else "NOT SET"
    print(f"Pipeline   last run {run['started_at'] if run else 'never'} · feeds ok {len(d.get('feeds_ok', []))} · "
          f"failed {len(d.get('feeds_failed', {}))} · web search {d.get('web_search')} · Claude judged {stats.get('judged', 0)} stories")
    print(f"Database   {conn.execute('SELECT COUNT(*) FROM stories').fetchone()[0]} stories · "
          f"{conn.execute('SELECT COUNT(*) FROM story_sources').fetchone()[0]} source items · "
          f"{conn.execute('SELECT COUNT(*) FROM newsletter_subscribers').fetchone()[0]} local newsletter rows")
    print(f"API keys   ANTHROPIC_API_KEY {env('ANTHROPIC_API_KEY')} · YOUTUBE_API_KEY {env('YOUTUBE_API_KEY')} · Higgsfield API keys {'set' if os.environ.get('HF_API_KEY_ID') and os.environ.get('HF_API_KEY_SECRET') else 'NOT SET'} "
          f"(adapter: {cfg['publishing']['video']['higgsfield']['adapter']})")
    print(f"Site       node_modules {'present' if (site / 'node_modules').exists() else 'MISSING'} · production build "
          f"{'present' if ((site / 'dist' / 'client' / 'index.html').exists() or (site / 'dist' / 'index.html').exists()) else 'not built'} · SITE_URL {env('SITE_URL')} · "
          f"PUBLICATION_EMAIL_DOMAIN {env('PUBLICATION_EMAIL_DOMAIN')} · PUBLIC_NEWSLETTER_ENDPOINT {env('PUBLIC_NEWSLETTER_ENDPOINT')} · "
          f"PUBLIC_ANALYTICS_ENDPOINT {env('PUBLIC_ANALYTICS_ENDPOINT')}")
    print(f"Articles   {arts or 'none'}\nVideos     {vids or 'none'}")
    print(f"Affiliates {len(cfg['affiliates'].get('products') or {})} products configured")
    print("Flags      " + " · ".join(f"{k}={'on' if v else 'off'}" for k, v in cfg["flags"].items()))


def cmd_analytics(cfg, args):
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    n = conn.execute("SELECT COUNT(*) FROM performance_metrics").fetchone()[0]
    pub = conn.execute("SELECT COUNT(*) FROM published_content").fetchone()[0]
    vp = conn.execute("SELECT COUNT(DISTINCT video_id) FROM video_posts").fetchone()[0]
    vm = conn.execute("SELECT COUNT(*) FROM video_metrics").fetchone()[0]
    print(f"Videos published: {vp}/10 of the first sprint · measurements logged: {vm} · details: python scripts/perf.py show")
    print(f"Published pieces logged: {pub} · performance rows: {n}")
    print("No site analytics provider is connected yet, so there is nothing to report. The site emits "
          "provider-independent events (page view, scroll depth, engaged time, share, newsletter signup, "
          "affiliate click, related click) once PUBLIC_ANALYTICS_ENDPOINT is set. No numbers are estimated here.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("top").add_argument("-n", type=int, default=20)
    sub.add_parser("story").add_argument("id", type=int)
    for name in ("watchlist", "sources", "status", "analytics"):
        sub.add_parser(name)
    args = ap.parse_args()
    cfg = load_config()
    globals()[f"cmd_{args.cmd}"](cfg, args)


if __name__ == "__main__":
    main()
