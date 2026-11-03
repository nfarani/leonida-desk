#!/usr/bin/env python3
"""Short-form video packages for /make, /video, /videos, /revise-video, /render and /published.

  python scripts/make_video.py init 1                # rank 1 on the hot list of the latest briefing
  python scripts/make_video.py init story:224 [--packet story-224-love-interview]
  python scripts/make_video.py check <video_id>      # validate, write the project files, set status
  python scripts/make_video.py show <video_id>
  python scripts/make_video.py list
  python scripts/make_video.py plan <video_id>       # scenes, generations, models, estimated cost
  python scripts/make_video.py produce <video_id> [--confirm]  # full production to final.mp4 via the Higgsfield CLI (paid)
  python scripts/make_video.py render <video_id> [--confirm]   # fallback: manual sheet, or the HTTP API adapter
  python scripts/make_video.py voices "Bro... imagine getting five stars in this." --names Dylan Knox Reid [--confirm]
  python scripts/make_video.py poll <video_id>       # api: collect finished generations
  python scripts/make_video.py ingest <video_id>     # clips in assets/ -> READY_FOR_REVIEW
  python scripts/make_video.py approve|reject <video_id> [--note "..."]
  python scripts/make_video.py publish <video_id> --platform youtube_shorts --url https://...
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import _path  # noqa: F401
from research import articles as A
from research import db, games, higgsfield, produce, video
from research.config import load_config, resolve

DESK_FIELDS = ("tier", "tier_reason", "gate", "treatment", "video_suitability", "visual_potential", "hook_strength",
               "recommendation_confidence", "momentum")


def _conn(cfg):
    return db.connect(resolve(cfg, cfg["settings"]["database_path"]))


def _write(cfg):
    """Save without re-running the checker's status logic (used while a render is in flight)."""
    def save(pkg):
        video.save(pkg, cfg)
    return save


def cmd_init(cfg, args):
    conn = _conn(cfg)
    if args.ref.startswith("story:"):
        sid = int(args.ref.split(":", 1)[1])
    else:
        # A bare number is the rank on the hot list of the latest run
        run = conn.execute("SELECT MAX(id) FROM runs WHERE finished_at IS NOT NULL").fetchone()[0]
        rows = conn.execute("SELECT id, desk FROM stories WHERE desk IS NOT NULL").fetchall()
        hit = [r["id"] for r in rows if (d := json.loads(r["desk"])).get("run_id") == run and d.get("desk_rank") == int(args.ref)]
        if not hit:
            sys.exit(f"Nothing at rank {args.ref} on the hot list of the latest briefing. "
                     "Use story:<id> to make a video from any stored story.")
        sid = hit[0]
    stories = {s.id: s for s in db.load_recent_stories(conn, datetime.now(timezone.utc) - timedelta(days=3650))}
    if sid not in stories:
        sys.exit(f"No story #{sid}.")
    story = stories[sid]
    games.tag(story, cfg)
    row = conn.execute("SELECT desk, opportunity_score, viral_score, saturation_score, freshness_score FROM stories WHERE id=?",
                       (sid,)).fetchone()
    desk = json.loads(row["desk"] or "{}")
    made = [p["video_id"] for p in video.all_packages(cfg) if p.get("story_id") == sid and p.get("status") != "REJECTED"]
    if made and not args.again:
        sys.exit(f"Story #{sid} already has a video package: {', '.join(made)}. Use /revise-video, or pass --again for a new angle.")
    # Reuse research: an evidence packet built for the article serves the video too
    existing = sorted(A.evidence_dir(cfg).glob("*.json")) if A.evidence_dir(cfg).exists() else []
    packet = None
    if args.packet:
        packet = A.load_packet(args.packet, cfg)
    else:
        for p in existing:
            cand = json.loads(p.read_text())
            if sid in (cand.get("story_ids") or [cand.get("story_id")]):
                packet = cand
                break
    if packet is None:
        packet = A.build_packet([story], cfg, angle_id="short")
        A.save_packet(packet, cfg)
        print("No evidence packet existed for this story, so a new one was started. Open the sources and add "
              "verified claims with scripts/article.py before writing the voiceover.")
    pkg = video.new_package(sid, packet, cfg, game=story.desk.get("game"), headline=story.headline)
    # Why this story: the desk's verdict and every gate check, kept with the package
    pkg["desk"] = {**{k: desk.get(k) for k in DESK_FIELDS}, "opportunity": row["opportunity_score"], "viral": row["viral_score"],
                   "saturation": row["saturation_score"], "freshness": row["freshness_score"],
                   "suggested_hook": story.editorial.get("hook"), "visual_premise": story.editorial.get("visual_premise")}
    pkg["treatment"] = desk.get("treatment")
    pkg["game_name"] = story.desk.get("game_name")
    pkg["topic"] = story.content_cluster
    base, k = pkg["video_id"], 2
    while (video.videos_dir(cfg) / pkg["video_id"] / "package.json").exists():   # a new angle never overwrites a package
        pkg["video_id"] = f"{base[:36]}-v{k}"
        k += 1
    d = video.videos_dir(cfg) / pkg["video_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "package.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n")
    facts = [c for c in packet["claims"] if c.get("kind") == "fact"]
    print(f"Video package: {d / 'package.json'}")
    print(f"Story #{sid}: {story.headline}")
    print(f"Hot list: {'rank ' + str(desk['desk_rank']) if desk.get('desk_rank') else 'not on the latest hot list'}")
    print(f"Suggested treatment: {desk.get('treatment')} · suggested hook: {story.editorial.get('hook')}")
    print(f"What the viewer sees (decide this first): {story.editorial.get('visual_premise') or 'not defined'}")
    print(f"Label (the video inherits it): {packet['story_label']} · evidence packet: {packet['packet_id']} "
          f"({len(facts)} verified claims)")
    for s in packet["sources"]:
        print(f"  {s['id']} {'opened' if s.get('opened') else 'NOT OPENED'} tier {s['tier']} {s['publisher']}: {s['url']}")
    for c in facts:
        print(f"  {c['id']}: {c['claim'][:110]}")


def cmd_check(cfg, args):
    pkg, _ = video.load(args.video_id, cfg)
    path, issues = video.save(pkg, cfg)
    print(f"{pkg['video_id']} · status {pkg['status']} · {video.runtime(pkg):.0f}s · "
          f"{len(video.voiceover_text(pkg).split())} words")
    for i in issues:
        print(f"  {i['level'].upper():7} {i['code']}: {i['detail']}")
    print(f"Project files: {path.parent}")


def cmd_show(cfg, args):
    pkg, path = video.load(args.video_id, cfg)
    print(video.render_markdown(pkg))


def cmd_list(cfg, args):
    pkgs = video.all_packages(cfg)
    if not pkgs:
        print("No video packages yet. Start one with /make <desk rank or story:ID>.")
    for p in pkgs:
        print(f"{p['status']:22} {p['verification_status']:24} {video.runtime(p):>3.0f}s  {p['video_id']}  {p.get('youtube_title', '')[:60]}")
    done = sum(p["status"] == "PUBLISHED" for p in pkgs)
    print(f"\n10-video sprint: {done}/10 published.")


def _ready(pkg):
    if pkg["status"] in ("IDEA", "SCRIPTED", "DRAFT"):
        sys.exit(f"This package is not ready (status {pkg['status']}). Run `check` and fix the errors first.")


def cmd_plan(cfg, args):
    pkg, _ = video.load(args.video_id, cfg)
    print(higgsfield.plan_text(pkg, cfg))


def cmd_render(cfg, args):
    pkg, path = video.load(args.video_id, cfg)
    _ready(pkg)
    try:
        print(higgsfield.submit(pkg, path.parent, cfg, confirm=args.confirm, save=_write(cfg)))
    except higgsfield.NotReady as exc:
        print(higgsfield.plan_text(pkg, cfg))
        print(f"\nThe API path is not ready: {exc}\n" + higgsfield.sheet(pkg, path.parent, cfg))
    video.save(pkg, cfg)


def cmd_produce(cfg, args):
    """The whole production: narration, clips, graphics, captions, sound and the final MP4."""
    pkg, path = video.load(args.video_id, cfg)
    _ready(pkg)
    if pkg["status"] in ("APPROVED", "PUBLISHED", "REJECTED"):
        sys.exit(f"This video is {pkg['status']}; it is not produced again.")
    print(produce.plan_text(pkg, cfg))
    if not args.confirm:
        print("\nNothing was generated. This spends Higgsfield credits: run again with --confirm to go ahead.")
        return
    try:
        final = produce.produce(pkg, path.parent, cfg, save=_write(cfg), output=args.output)
    except produce.ProduceError as exc:
        video.save(pkg, cfg)
        sys.exit(f"\nProduction stopped: {exc}\nFinished steps are kept; run the same command again to continue.")
    print(f"\n{pkg['video_id']} · {pkg['status']} · {pkg['render']['seconds']}s · {pkg['render']['generations']} generations · "
          f"about {pkg['render']['cost']} credits\nFinal video: {final}")


def cmd_voices(cfg, args):
    """Audition narrator voices: the same line in several preset voices, saved for the editor to hear.
    Choosing the channel's voice is a listening decision; this makes it a one-minute one."""
    out = resolve(cfg, "outputs/voices")
    out.mkdir(parents=True, exist_ok=True)
    c = cfg["publishing"]["video"]["production"]["voice"]
    listed = produce.hf("voices", "list")
    listed = listed if isinstance(listed, list) else next(v for v in listed.values() if isinstance(v, list))
    ids = {v["name"].lower(): v for v in listed}
    missing = [n for n in args.names if n.lower() not in ids]
    if missing:
        sys.exit(f"No preset voice named {missing}. See `higgsfield voices list`.")
    cost = produce.estimate(c["model"], ["--prompt", args.line, "--variant", c["variant"], "--voice_id", ids[args.names[0].lower()]["id"],
                                         "--voice_type", "preset"])
    print(f"{len(args.names)} voices x about {cost} credits each. Line: {args.line}")
    if not args.confirm:
        print("Nothing was generated: add --confirm to spend the credits.")
        return
    import urllib.request
    for name in args.names:
        v = ids[name.lower()]
        if (out / f"{v['name']}.mp3").exists():
            print(f"  {v['name']:10} already auditioned: {out / (v['name'] + '.mp3')}")
            continue
        try:
            job = produce.hf("generate", "create", c["model"], "--prompt", produce.speak(args.line), "--variant", c["variant"],
                             "--voice_id", v["id"], "--voice_type", v["voice_type"], "--wait")
        except produce.ProduceError as exc:
            print(f"  {v['name']:10} skipped: this voice failed on the {c['variant']} engine ({str(exc)[-60:]})")
            continue
        job = job[0] if isinstance(job, list) else job
        meta = (job.get("params") or {}).get("voice") or {}
        path = out / f"{v['name']}.mp3"
        urllib.request.urlretrieve(job["result_url"], path)
        print(f"  {v['name']:10} {meta.get('gender', '?'):7} {meta.get('age', '?'):12} id {v['id']}  {path}")
    print("Listen, then set video.production.voice (name and id) in config/publishing.yaml.")


def cmd_poll(cfg, args):
    pkg, path = video.load(args.video_id, cfg)
    try:
        print(higgsfield.poll(pkg, path.parent, cfg, save=_write(cfg)))
    except higgsfield.NotReady as exc:
        sys.exit(f"The API path is not ready: {exc}")
    video.save(pkg, cfg)


def cmd_ingest(cfg, args):
    pkg, path = video.load(args.video_id, cfg)
    _ready(pkg)
    have, missing = higgsfield.ingest(pkg, path.parent, cfg)
    video.save(pkg, cfg)
    print(f"{pkg['video_id']} · status {pkg['status']} · generated shots with an asset: {have or 'none'} · missing: {missing or 'none'}")
    if missing:
        print(f"Save the missing clips as {path.parent / 'assets'}/shot-<n>.mp4 and run ingest again.")


def cmd_approve(cfg, args):
    pkg, _ = video.load(args.video_id, cfg)
    if pkg["status"] != "READY_FOR_REVIEW":
        sys.exit(f"Only a READY_FOR_REVIEW package can be approved (status {pkg['status']}).")
    video.set_status(pkg, "APPROVED", args.note or "approved by the editor")
    video.save(pkg, cfg)
    print(f"{pkg['video_id']} · APPROVED. Nothing is uploaded by this command.")


def cmd_reject(cfg, args):
    pkg, _ = video.load(args.video_id, cfg)
    video.set_status(pkg, "REJECTED", args.note or "rejected by the editor")
    video.save(pkg, cfg)
    print(f"{pkg['video_id']} · REJECTED.")


def cmd_publish(cfg, args):
    """Record that the editor posted the video. This uploads nothing: it logs the post, starts the
    story's cooldown and opens the performance record."""
    pkg, _ = video.load(args.video_id, cfg)
    if pkg["status"] not in ("APPROVED", "PUBLISHED"):
        sys.exit(f"Approve the video before logging a post (status {pkg['status']}).")
    conn = _conn(cfg)
    when = args.published_at or A.iso(A.now_utc())
    hook = pkg["hooks"][pkg["recommended_hook"]] if pkg.get("hooks") else ""
    conn.execute("""INSERT INTO video_posts(video_id, story_id, platform, url, published_at, game, topic,
                    treatment, hook_style, visual_style, seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(video_id, platform) DO UPDATE SET url=excluded.url, published_at=excluded.published_at""",
                 (pkg["video_id"], pkg["story_id"], args.platform, args.url, when, pkg.get("game_name") or pkg.get("game"),
                  pkg.get("topic"), pkg.get("treatment"), pkg.get("hook_style"), pkg.get("visual_style"), video.runtime(pkg)))
    if pkg["status"] != "PUBLISHED":
        db.mark_used(conn, pkg["story_id"], args.platform, args.url, pkg.get("youtube_title"), pkg.get("treatment"), None)
    conn.commit()
    pkg.setdefault("posts", []).append({"platform": args.platform, "url": args.url, "published_at": when, "hook": hook})
    if args.url and (args.platform == "youtube_shorts" or not pkg.get("public_url")):
        pkg["public_url"] = args.url          # what the site's Videos page links to
    video.set_status(pkg, "PUBLISHED", f"posted on {args.platform}")
    video.save(pkg, cfg)
    n = conn.execute("SELECT COUNT(DISTINCT video_id) FROM video_posts").fetchone()[0]
    print(f"{pkg['video_id']} · PUBLISHED on {args.platform}. Story #{pkg['story_id']} is on cooldown.")
    print(f"10-video sprint: {n}/10 published. Log numbers with: python scripts/perf.py log {pkg['video_id']} {args.platform} --checkpoint 1h --views N ...")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("ref"); p.add_argument("--packet"); p.add_argument("--again", action="store_true")
    for name in ("check", "show", "plan", "poll", "ingest"):
        sub.add_parser(name).add_argument("video_id")
    for name in ("render", "produce"):
        p = sub.add_parser(name); p.add_argument("video_id"); p.add_argument("--confirm", action="store_true")
    p.add_argument("--output", default="final.mp4", help="file name for the export, e.g. final_v2.mp4 (earlier exports are kept)")
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("video_id"); p.add_argument("--note")
    p = sub.add_parser("publish"); p.add_argument("video_id")
    p.add_argument("--platform", required=True, choices=["youtube_shorts", "tiktok", "instagram", "youtube", "other"])
    p.add_argument("--url"); p.add_argument("--published-at", help="ISO time; default now")
    p = sub.add_parser("voices"); p.add_argument("line"); p.add_argument("--names", nargs="+", required=True)
    p.add_argument("--confirm", action="store_true")
    sub.add_parser("list")
    args = ap.parse_args()
    cfg = load_config()
    globals()[f"cmd_{args.cmd}"](cfg, args)


if __name__ == "__main__":
    main()
