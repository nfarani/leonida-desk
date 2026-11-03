"""Orchestrates DISCOVER -> NORMALISE -> CLUSTER -> VERIFY -> SCORE -> RANK -> HOT LIST -> SAVE."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, llm
from .categorise import categorise
from .cluster import cluster
from .community import content_type
from .config import resolve
from .discover import discover
from .games import tag as tag_game
from .normalise import normalise
from .rank import CHATTER_REASON, held_back, rank
from .recommend import recommend
from .report import render, to_json
from .score import compute_deterministic, finalise, preliminary
from .verify import verify


def run(cfg: dict, use_llm: bool = True, use_web_search: bool = True, items_override=None,
        db_path: str | Path | None = None, out_dir: str | Path | None = None, log=print) -> tuple[Path, list]:
    now = datetime.now(timezone.utc)
    st = cfg["settings"]
    conn = db.connect(db_path or resolve(cfg, st["database_path"]))
    run_id = db.create_run(conn)
    llm_ok = use_llm and llm.available()
    stats: dict = {"warnings": []}
    if not llm_ok:
        stats["warnings"].append("heuristic mode: no Claude editorial judgement (set ANTHROPIC_API_KEY)")

    log("DISCOVER")
    if items_override is not None:
        raw, disc = items_override, {"feeds_ok": ["fixture"], "feeds_failed": {}, "feeds_skipped": [],
                                     "web_search": "disabled (fixture run)"}
        stats["warnings"].append("FIXTURE RUN: synthetic test data, not real news")
    else:
        raw, disc = discover(cfg, use_web_search=use_web_search and llm_ok, log=log)
    stats["discovery"] = disc
    if items_override is None and not disc["feeds_ok"] and "results" not in str(disc.get("web_search")):
        stats["warnings"].append("ALL discovery sources failed: briefing reflects stored stories only")

    log("NORMALISE")
    new, known, stats["normalise"] = normalise(raw, cfg, db.known_urls(conn))
    db.refresh_engagement(conn, known)

    log("CLUSTER")
    existing = db.load_recent_stories(conn, now - timedelta(hours=st["clustering"]["match_window_hours"]))
    adj = (lambda pairs: llm.adjudicate_pairs(cfg, pairs)) if llm_ok else None
    stories, stats["cluster"] = cluster(new, existing, cfg, adjudicate=adj)

    log("VERIFY")
    relabelled = verify(stories, cfg)
    for s in stories:
        if s.new_items or s.absorbed or s.id is None:
            s.content_cluster = categorise(s, cfg)
    new_ids = {id(i) for i in new}
    by_type: dict[str, int] = {}
    new_by_type: dict[str, int] = {}
    for s in stories:
        for i in s.items:
            t = content_type(i, cfg)
            if t:
                by_type[t] = by_type.get(t, 0) + 1
                if id(i) in new_ids:
                    new_by_type[t] = new_by_type.get(t, 0) + 1
    stats["community"] = {"by_type": by_type, "new_by_type": new_by_type, **relabelled}

    for s in stories:
        tag_game(s, cfg)

    log("SCORE")
    used = db.used_story_tokens(conn, now - timedelta(days=14))
    for s in stories:
        compute_deterministic(s, cfg, now, used)
    live = [s for s in stories if not held_back(s, cfg, now)]
    live.sort(key=lambda s: .5 * s.dims["freshness"] + .3 * s.dims["existing_demand"]
              + .2 * s.dims["credibility"], reverse=True)
    # A story judged on an earlier run keeps that judgement until it gains a source
    for s in stories:
        if s.judged_by == "claude" and (s.new_items or s.absorbed):
            s.judged_by, s.editorial = "heuristic", {}
            for k in db.JUDGED_KEYS:
                s.dims.pop(k, None)
            s.desk.pop("out_of_scope", None)
    size, calls = st["llm"]["editorial_batch_size"], st["llm"].get("editorial_batches", 1)
    # Claude judges at least twice as many candidates as the hot list holds, so a longer list is not
    # filled with keyword-scored stories
    calls = max(calls, -(-2 * st["ranking"]["hot_list"]["count"] // size))
    # The likeliest candidates go to Claude first; the rest wait for a later run
    todo = sorted((s for s in live if s.judged_by != "claude"), key=lambda s: -preliminary(s, cfg))[: size * calls]
    stats["judged"] = 0
    if llm_ok:
        for n in range(0, len(todo), size):
            stats["judged"] += llm.editorial(cfg, todo[n:n + size])
    batch_ids = {id(s) for s in todo[:size]}
    for s in stories:
        finalise(s, cfg, now, check_youtube=id(s) in batch_ids)

    log("RANK / HOT LIST")
    ranked, held = rank(stories, cfg, now, db.cluster_last_used(conn))
    chatter = [s for s in held if s.held_back_reason == CHATTER_REASON]
    chatter.sort(key=lambda s: s.dims.get("existing_demand", 0), reverse=True)
    stats["community"]["held_as_chatter"] = len(chatter)
    stats["community"]["top_chatter"] = [s.headline[:90] for s in chatter[:5] if s.freshness >= 0.3]
    recs, view = recommend(ranked, cfg, now, stories)
    stats["hot_list_count"] = cfg["settings"]["ranking"]["hot_list"]["count"]
    stats["desk"] = {"hot": len(view["hot"]), "radar": len(view["radar"]), "skipped": len(view["skipped"])}

    log("SAVE")
    for s in stories:
        s.desk["run_id"] = run_id
        db.save_story(conn, s)
    for i, (s, p) in enumerate(recs, 1):
        db.insert_recommendation(conn, run_id, i, s, p)
    out = Path(out_dir) if out_dir else resolve(cfg, st["briefings_dir"])
    out.mkdir(parents=True, exist_ok=True)
    stem = now.strftime("%Y-%m-%d_%H%M")
    md_path = out / f"briefing_{stem}.md"
    md_path.write_text(render(recs, held, stats, now, view))
    (out / f"briefing_{stem}.json").write_text(to_json(recs, now, view))
    (out / "latest.md").write_text(md_path.read_text())
    db.finish_run(conn, run_id, stats, str(md_path))
    conn.commit()
    conn.close()
    return md_path, recs
