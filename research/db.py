"""SQLite persistence (SAVE stage + loading prior state for dedup/cooldown)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .models import Item, Story
from .text import tokens


DESK_KEYS = ["desk_rank", "run_id", "bucket", "game", "game_name", "momentum", "recommendation_confidence",
             "skip", "why_now"]
JUDGED_KEYS = ["curiosity_gap", "surprise", "significance", "visual_potential", "emotional_reaction", "shareability",
               "comment_potential", "hook_strength"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((ROOT / "data" / "schema.sql").read_text())
    _migrate(conn)
    return conn


def _migrate(conn) -> None:
    """Additive migrations only: new nullable columns on existing tables."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(recommendations)")}
    for col in ("editorial_bucket", "recommended_output"):
        if col not in have:
            conn.execute(f"ALTER TABLE recommendations ADD COLUMN {col} TEXT")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(stories)")}
    for col in ("desk", "judgement"):
        if col not in have:
            conn.execute(f"ALTER TABLE stories ADD COLUMN {col} TEXT")


# ---------- sources / clusters
def upsert_source(conn, domain: str, name: str, source_type: str, tier: int) -> int:
    row = conn.execute("SELECT id FROM sources WHERE domain=?", (domain,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO sources(name, domain, source_type, tier, created_at) VALUES (?,?,?,?,?)",
        (name, domain, source_type, tier, iso(now())))
    return cur.lastrowid


def ensure_cluster(conn, slug: str) -> None:
    conn.execute("INSERT OR IGNORE INTO content_clusters(slug, label, created_at) VALUES (?,?,?)",
                 (slug, slug.replace("_", " ").title(), iso(now())))


def cluster_last_used(conn) -> dict[str, datetime]:
    rows = conn.execute("SELECT slug, last_used_at FROM content_clusters WHERE last_used_at IS NOT NULL")
    return {r["slug"]: parse_iso(r["last_used_at"]) for r in rows}


# ---------- items / stories
def known_urls(conn) -> set[str]:
    return {r["url"] for r in conn.execute("SELECT url FROM story_sources")}


def refresh_engagement(conn, items: list[Item]) -> int:
    n = 0
    for it in items:
        if it.engagement:
            n += conn.execute("UPDATE story_sources SET engagement=? WHERE url=?",
                              (json.dumps(it.engagement), it.url)).rowcount
    return n


def _row_to_item(r) -> Item:
    return Item(url=r["url"], title=r["title"], snippet=r["snippet"] or "", publisher=r["publisher"] or "",
                domain="", source_type=r["source_type"], tier=r["tier"],
                discovered_via=r["discovered_via"] or "", published_at=parse_iso(r["published_at"]),
                fetched_at=parse_iso(r["fetched_at"]), engagement=json.loads(r["engagement"] or "{}"))


def load_recent_stories(conn, since: datetime) -> list[Story]:
    stories = []
    rows = conn.execute("SELECT * FROM stories WHERE last_updated_at >= ? OR status='used'", (iso(since),))
    for r in rows:
        items = [_row_to_item(x) for x in conn.execute(
            "SELECT * FROM story_sources WHERE story_id=?", (r["id"],))]
        if not items:
            continue
        stories.append(Story(
            items=items, id=r["id"], headline=r["headline"], summary=r["summary"] or "",
            first_seen_at=parse_iso(r["first_seen_at"]), last_updated_at=parse_iso(r["last_updated_at"]),
            last_material_update_at=parse_iso(r["last_material_update_at"]),
            verification_status=r["verification_status"], previous_status=r["verification_status"],
            content_cluster=r["content_cluster"] or "breaking_news", status=r["status"],
            used_at=parse_iso(r["used_at"]), reasoning=r["reasoning"] or ""))
        # Claude's judgement is kept until the story gains a source, so a story judged yesterday is not
        # demoted to keyword scoring today just because it fell out of the batch.
        j = json.loads(r["judgement"] or "null")
        if j:
            s = stories[-1]
            s.dims.update(j.get("dims", {}))
            s.editorial, s.judged_by = j.get("editorial", {}), "claude"
            s.desk.update({k: v for k, v in j.get("desk", {}).items() if v})
    return stories


def used_story_tokens(conn, since: datetime) -> list[tuple[int, set[str]]]:
    rows = conn.execute("""SELECT id, headline FROM stories
                           WHERE status='used' AND used_at >= ?""", (iso(since),))
    return [(r["id"], tokens(r["headline"])) for r in rows]


def save_story(conn, s: Story) -> int:
    best = s.best_item()
    vals = dict(
        headline=s.headline, summary=s.summary, source_url=best.url, source_name=best.publisher,
        source_type=best.source_type, published_at=iso(s.published_at), first_seen_at=iso(s.first_seen_at),
        last_updated_at=iso(s.last_updated_at), last_material_update_at=iso(s.last_material_update_at),
        verification_status=s.verification_status, content_cluster=s.content_cluster,
        freshness_score=round(s.freshness, 4), viral_score=round(s.viral, 2),
        saturation_score=round(s.saturation, 2), opportunity_score=round(s.opportunity, 2),
        score_breakdown=json.dumps({k: round(v, 3) for k, v in s.dims.items()}),
        reasoning=s.reasoning, status=s.status, used_at=iso(s.used_at),
        fingerprint=" ".join(sorted(tokens(s.headline))),
        desk=json.dumps({k: s.desk.get(k) for k in DESK_KEYS if s.desk.get(k) is not None}),
        judgement=json.dumps({"dims": {k: s.dims[k] for k in JUDGED_KEYS if k in s.dims}, "editorial": s.editorial,
                              "desk": {k: s.desk.get(k) for k in ("out_of_scope", "game_name", "parent_event")}})
        if s.judged_by == "claude" else None)
    ensure_cluster(conn, s.content_cluster)
    if s.id is None:
        cols = ",".join(vals)
        cur = conn.execute(f"INSERT INTO stories({cols}) VALUES ({','.join('?' * len(vals))})",
                           list(vals.values()))
        s.id = cur.lastrowid
    else:
        sets = ",".join(f"{k}=?" for k in vals)
        conn.execute(f"UPDATE stories SET {sets} WHERE id=?", [*vals.values(), s.id])
    for dup in s.absorbed:
        if dup.id is None:
            continue
        # Keep the absorbed row as an empty tombstone (history stays intact); its sources move here.
        conn.execute("UPDATE story_sources SET story_id=? WHERE story_id=?", (s.id, dup.id))
        conn.execute("UPDATE stories SET status='stale', reasoning=? WHERE id=?",
                     (f"merged into story #{s.id}", dup.id))
    for it in s.new_items:
        src_id = upsert_source(conn, it.domain or it.publisher.lower(), it.publisher, it.source_type, it.tier)
        conn.execute("""INSERT OR IGNORE INTO story_sources
            (story_id, source_id, url, title, snippet, publisher, source_type, tier, discovered_via,
             published_at, fetched_at, engagement) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (s.id, src_id, it.url, it.title, it.snippet, it.publisher, it.source_type, it.tier,
             it.discovered_via, iso(it.published_at), iso(it.fetched_at), json.dumps(it.engagement)))
    return s.id


# ---------- runs / recommendations / publishing
def create_run(conn) -> int:
    return conn.execute("INSERT INTO runs(started_at) VALUES (?)", (iso(now()),)).lastrowid


def finish_run(conn, run_id: int, stats: dict, report_path: str) -> None:
    conn.execute("UPDATE runs SET finished_at=?, stats=?, report_path=? WHERE id=?",
                 (iso(now()), json.dumps(stats), report_path, run_id))


def insert_recommendation(conn, run_id: int, rank: int, s: Story, post_now: bool) -> int:
    e = s.editorial
    return conn.execute("""INSERT INTO recommendations
        (run_id, story_id, rank, opportunity_score, rank_score, post_now, why_care, recommended_format,
         recommended_angle, suggested_hook, risk_caveat, created_at, editorial_bucket, recommended_output)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, s.id, rank, round(s.opportunity, 2), round(s.rank_score, 2), int(post_now),
         e.get("why_care"), e.get("format"), e.get("angle"), e.get("hook"), e.get("risk"),
         iso(now()), s.desk.get("bucket"), s.desk.get("output"))).lastrowid


def mark_used(conn, story_id: int, platform: str, url: str | None, title: str | None,
              fmt: str | None, recommendation_id: int | None) -> None:
    t = iso(now())
    conn.execute("""INSERT INTO published_content(story_id, recommendation_id, platform, url, title, format,
                    published_at) VALUES (?,?,?,?,?,?,?)""",
                 (story_id, recommendation_id, platform, url, title, fmt, t))
    conn.execute("UPDATE stories SET status='used', used_at=? WHERE id=?", (t, story_id))
    conn.execute("""UPDATE content_clusters SET last_used_at=?
                    WHERE slug=(SELECT content_cluster FROM stories WHERE id=?)""", (t, story_id))
