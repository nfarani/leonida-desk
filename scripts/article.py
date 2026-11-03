#!/usr/bin/env python3
"""Article workflow helpers for the /article command. Never publishes.

  python scripts/article.py packet 3                 # rank 3 of the latest briefing
  python scripts/article.py packet story:224 --also 205 232 --angle "..." --angle-id love-interview
  python scripts/article.py packet topic:weather     # evergreen topic from config/evergreen.yaml
  python scripts/article.py claim <packet> --source s2 --claim "..." --evidence "..." [--quote "..."]
  python scripts/article.py opened <packet> s1 s2    # mark sources as opened and rechecked
  python scripts/article.py conflict <packet> "VGC and Polygon give different first names"
  python scripts/article.py check <slug>             # fact-check, score, gate, restamp the file
  python scripts/article.py list
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import _path  # noqa: F401
from research import articles as A
from research import db, desk
from research.config import load_config, resolve


def _stories(cfg, ids):
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    stories = db.load_recent_stories(conn, datetime.now(timezone.utc) - timedelta(days=3650))
    by_id = {s.id: s for s in stories}
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"No story with id {missing} (merged stories keep only the surviving id).")
    return [by_id[i] for i in ids], stories, conn


def cmd_packet(cfg, args):
    ref, bucket, angle_id = args.ref, args.bucket, args.angle_id
    if ref.startswith("topic:"):
        tid = ref.split(":", 1)[1]
        _, stories, _ = _stories(cfg, [])
        topic = next((t for t in desk.evergreen_topics(stories, cfg) if t["topic_id"] == tid), None)
        if not topic:
            sys.exit(f"Topic '{tid}' does not have enough stored, well-labelled evidence yet.")
        ids = [x["story_id"] for x in topic["supporting_stories"]]
        bucket, angle_id = "EVERGREEN", f"evergreen:{tid}"
        args.angle = args.angle or topic["title"]
    elif ref.startswith("story:"):
        ids = [int(ref.split(":", 1)[1])]
    else:
        conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
        row = conn.execute("""SELECT story_id, editorial_bucket FROM recommendations
                              WHERE run_id=(SELECT MAX(run_id) FROM recommendations) AND rank=?""",
                           (int(ref),)).fetchone()
        if not row:
            sys.exit(f"No recommendation with rank {ref} in the latest run.")
        ids, bucket = [row["story_id"]], bucket or row["editorial_bucket"]
    ids += [int(i) for i in args.also or []]
    stories, _, _ = _stories(cfg, ids)
    packet = A.build_packet(stories, cfg, angle=args.angle or "", angle_id=angle_id, bucket=bucket)
    path = A.save_packet(packet, cfg)
    print(f"Evidence packet: {path}")
    print(f"Story label (ceiling for the article): {packet['story_label']} · bucket: {packet['editorial_bucket']}")
    for s in packet["sources"]:
        print(f"  {s['id']}  tier {s['tier']}  {s['publisher']}: {s['title'][:80]}\n      {s['url']}")
    print("\nNext: open each source, then add verified claims with `article.py claim`. "
          "Seed claims are headline-only and do not count as evidence.")


def cmd_claim(cfg, args):
    p = A.load_packet(args.packet, cfg)
    c = A.add_claim(p, args.claim, args.source, args.evidence, args.quote, args.verification)
    A.save_packet(p, cfg)
    print(f"Added {c['id']} ({c['verification']})")


def cmd_opened(cfg, args):
    p = A.load_packet(args.packet, cfg)
    now = A.iso(A.now_utc())
    for s in p["sources"]:
        if s["id"] in args.sources:
            s["opened"], s["opened_at"] = True, now
    A.save_packet(p, cfg)
    print(f"Marked opened: {', '.join(args.sources)}")


def cmd_conflict(cfg, args):
    p = A.load_packet(args.packet, cfg)
    p["conflicts"].append({"description": args.description, "resolved": False})
    A.save_packet(p, cfg)
    print("Conflict recorded; the article will need review until it is resolved.")


def print_report(meta, report):
    print(f"\n{meta['slug']}  ·  status {meta['status']}  ·  gate {report['gate']}")
    print(f"originality {report['originality_score']}/100 · quality {report['quality_score']}/100 · "
          f"source overlap {report['source_overlap']:.0%}")
    for r in report["gate_reasons"]:
        print(f"  gate: {r}")
    for i in report["issues"]:
        print(f"  {i['level'].upper():7} {i['code']}: {i['detail']}")
    if report["duplicates"]:
        print(f"  duplicates: {', '.join(report['duplicates'])}")


def cmd_check(cfg, args):
    meta, body, _ = A.load_article(args.slug, cfg)
    packet = A.load_packet(meta["evidence_packet"], cfg)
    path, report = A.save_article(meta, body, packet, cfg)
    meta, _, _ = A.load_article(args.slug, cfg)
    print_report(meta, report)
    print(f"\nSaved: {path}")
    if args.json:
        print(json.dumps(report, indent=2))


def cmd_list(cfg, args):
    for meta, _, _ in A.all_articles(cfg):
        print(f"{meta.get('status', '?'):16} {meta.get('editorial_bucket', '?'):10} {meta.get('gate', ''):22} {meta.get('slug')}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("packet"); p.add_argument("ref"); p.add_argument("--also", nargs="*")
    p.add_argument("--angle"); p.add_argument("--angle-id"); p.add_argument("--bucket", choices=desk.BUCKETS)
    p = sub.add_parser("claim"); p.add_argument("packet"); p.add_argument("--source", required=True)
    p.add_argument("--claim", required=True); p.add_argument("--evidence", required=True)
    p.add_argument("--quote"); p.add_argument("--verification")
    p = sub.add_parser("opened"); p.add_argument("packet"); p.add_argument("sources", nargs="+")
    p = sub.add_parser("conflict"); p.add_argument("packet"); p.add_argument("description")
    p = sub.add_parser("check"); p.add_argument("slug"); p.add_argument("--json", action="store_true")
    sub.add_parser("list")
    args = ap.parse_args()
    cfg = load_config()
    {"packet": cmd_packet, "claim": cmd_claim, "opened": cmd_opened, "conflict": cmd_conflict,
     "check": cmd_check, "list": cmd_list}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
