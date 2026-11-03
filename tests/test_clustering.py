"""Event fingerprints: rewrites of one event merge, unrelated stories stay apart."""
from datetime import datetime, timedelta, timezone

from research import db
from research.cluster import cluster
from research.normalise import normalise
from research.pipeline import run


def clustered(cfg, items, existing=None):
    new, _, _ = normalise(items, cfg, set())
    return cluster(new, existing or [], cfg)


def test_same_pegi_event_with_very_different_headlines(cfg, make):
    stories, stats = clustered(cfg, [
        make("PEGI removes GTA VI rating after explicit-content details appear", "tierone-a.test", hours_ago=5),
        make("GTA 6 rating pulled after revealing sex scenes and drug use", "tierone-b.test", hours_ago=4),
        make("GTA 6's 18+ age rating reveals cocaine can be used at any time", "tiertwo.test", hours_ago=3),
    ])
    assert len(stories) == 1 and len(stories[0].items) == 3


def test_same_interview_rewritten_by_several_outlets(cfg, make):
    stories, _ = clustered(cfg, [
        make("Dan Houser still hasn't seen GTA 6: 'I will try and avoid it'", "tierone-a.test", hours_ago=9),
        make("Ex-Rockstar boss Dan Houser doesn't plan to play GTA 6", "tierone-b.test", hours_ago=8),
        make("Rockstar co-founder Dan Houser is avoiding GTA 6 so it doesn't distract him", "tiertwo.test",
             hours_ago=4),
    ])
    assert len(stories) == 1 and len(stories[0].items) == 3


def test_names_not_in_config_are_still_matched(cfg, make):
    stories, _ = clustered(cfg, [
        make("Studio veteran Maxine Quillfeather explains the GTA 6 map philosophy", "tierone-a.test", hours_ago=6),
        make("GTA 6 world was built 'like a theme park', says Maxine Quillfeather", "tierone-b.test", hours_ago=5),
    ])
    assert len(stories) == 1


def test_unrelated_stories_sharing_generic_words_stay_separate(cfg, make):
    stories, stats = clustered(cfg, [
        make("Rockstar confirms GTA 6 weather system overhaul", "tierone-a.test", hours_ago=9),
        make("Rockstar co-founder Sam Houser pulls out of GTA 6 interview", "tierone-b.test", hours_ago=8),
        make("Rockstar co-founder Dan Houser says he will avoid GTA 6", "tierone-a.test", hours_ago=7),
        make("Rockstar GTA 6 soundtrack leak names two artists", "tiertwo.test", hours_ago=6),
        make("Rockstar GTA 6 age rating confirmed as 18+ in Europe", "tierone-b.test", hours_ago=5),
        make("GTA 6 Rockstar collector's edition sells out", "tiertwo.test", hours_ago=4),
    ])
    assert len(stories) == 6
    assert stats["merged"] == 0


def test_same_topic_weeks_apart_is_not_the_same_event(cfg, make):
    stories, _ = clustered(cfg, [
        make("PEGI removes GTA VI rating after explicit-content details appear", "tierone-a.test", hours_ago=150),
        make("GTA 6 rating pulled after revealing sex scenes and drug use", "tierone-b.test", hours_ago=2),
    ])
    assert len(stories) == 2


def test_late_syndicated_coverage_does_not_reset_freshness(cfg, make):
    # A rewrite adds no evidence. (A second tier-1 outlet WOULD change the label, and a label change
    # is a material update under CLAUDE.md section 3; that case is not what this test covers.)
    title = "Synthetic Studio delays GTA 6 to Zeptember 2031"
    _, recs = run(cfg, use_llm=False, items_override=[
        make(title, "tierone-a.test", hours_ago=30, path="orig"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio says", "tierone-b.test", hours_ago=29, path="b")])
    first = recs[0][0]
    fresh, published = first.freshness, first.published_at
    assert fresh < 0.4
    _, recs2 = run(cfg, use_llm=False, items_override=[
        make(title + ": what we know", "tiertwo.test", hours_ago=0, path="syndicated")])
    again = recs2[0][0]
    assert len(recs2) == 1 and again.id == first.id and len(again.items) == 3
    assert abs((again.published_at - published).total_seconds()) < 1
    assert again.last_material_update_at is None
    assert again.freshness <= fresh


def test_first_official_source_still_counts_as_a_development(cfg, make):
    title = "Synthetic Studio delays GTA 6 to Zeptember 2031"
    _, recs = run(cfg, use_llm=False, items_override=[
        make(title, "tierone-a.test", hours_ago=30, path="orig"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio says", "tierone-b.test", hours_ago=29, path="b")])
    fresh = recs[0][0].freshness
    _, recs2 = run(cfg, use_llm=False, items_override=[
        make("Synthetic Studio confirms GTA 6 Zeptember 2031 delay", "official.test", "primary", hours_ago=0,
             path="official")])
    again = recs2[0][0]
    assert again.verification_status == "CONFIRMED" and again.freshness > fresh


def test_duplicate_stories_already_in_db_merge_and_keep_every_source(cfg, make):
    # Simulate the old behaviour: the same event stored as two stories by two earlier runs.
    conn = db.connect(cfg["settings"]["database_path"])
    a, _ = clustered(cfg, [
        make("PEGI removes GTA VI rating after explicit-content details appear", "tierone-a.test", hours_ago=20,
             path="a1")])
    b, _ = clustered(cfg, [
        make("GTA 6 rating pulled after revealing sex scenes and drug use", "tierone-b.test", hours_ago=6, path="b1"),
        make("GTA 6 rating pulled after it revealed sex scenes and drug use", "tiertwo.test", hours_ago=5, path="b2")])
    early = datetime.now(timezone.utc) - timedelta(hours=19)
    a[0].first_seen_at = early
    for s in (b[0], a[0]):
        s.verification_status = "CREDIBLE_RUMOUR"
        db.save_story(conn, s)
    conn.commit()
    conn.close()
    old_id, new_id = b[0].id, a[0].id

    path, recs = run(cfg, use_llm=False, items_override=[])
    assert len(recs) == 1
    merged = recs[0][0]
    assert {i.url.rsplit("/", 1)[-1] for i in merged.items} == {"a1", "b1", "b2"}
    assert merged.id == old_id                                   # the older db row survives
    assert abs((merged.first_seen_at - early).total_seconds()) < 1  # earliest discovery time kept
    assert merged.published_at == min(i.published_at for i in merged.items)
    assert merged.verification_status == "HIGH_CONFIDENCE_REPORT"  # strongest label the combined evidence allows
    assert merged.last_material_update_at is None                 # a merge is not a new development
    assert "Merged this run:** 1 stories" in path.read_text()

    conn = db.connect(cfg["settings"]["database_path"])
    rows = conn.execute("SELECT story_id FROM story_sources").fetchall()
    assert {r["story_id"] for r in rows} == {old_id} and len(rows) == 3
    tomb = conn.execute("SELECT status, reasoning FROM stories WHERE id=?", (new_id,)).fetchone()
    assert tomb["status"] == "stale" and f"#{old_id}" in tomb["reasoning"]
    conn.close()

    # A second run finds nothing left to merge
    path2, recs2 = run(cfg, use_llm=False, items_override=[])
    assert len(recs2) == 1 and "No duplicate stories found" in path2.read_text()


def test_borderline_pairs_are_reported_not_merged_without_claude(cfg, make):
    stories, stats = clustered(cfg, [
        make("GTA 6 weather system adds hurricanes, Rockstar says", "tierone-a.test", hours_ago=5),
        make("Hurricanes in GTA 6 will reshape parts of the map", "tierone-b.test", hours_ago=4),
    ])
    assert len(stories) == 2 and stats["merged"] == 0
    assert len(stats["probable_duplicates"]) == 1

    # With Claude available and agreeing, the same pair merges
    stories, stats = cluster(*[normalise([
        make("GTA 6 weather system adds hurricanes, Rockstar says", "tierone-a.test", hours_ago=5),
        make("Hurricanes in GTA 6 will reshape parts of the map", "tierone-b.test", hours_ago=4),
    ], cfg, set())[0]], [], cfg, adjudicate=lambda pairs: [True] * len(pairs))
    assert len(stories) == 1 and stats["llm_merged"] == 1


def test_story_with_no_publication_date_is_held_back(cfg, make):
    undated = make("GTA 6 trailer revealed with synthetic release window", "tiertwo.test", path="old")
    undated.published_at = None
    path, recs = run(cfg, use_llm=False, items_override=[
        undated, make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", path="d1")])
    assert [s.headline for s, _ in recs] == ["Synthetic Studio delays GTA 6 to Zeptember 2031"]
    assert "no publication date on any source" in path.read_text()
