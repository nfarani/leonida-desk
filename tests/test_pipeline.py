from research import llm
from research.cluster import cluster
from research.db import connect, mark_used
from research.models import Story
from research.normalise import normalise
from research.pipeline import run
from research.text import similarity, tokens
from research.verify import clip, evidence, heuristic_label


def test_weights_total_100(cfg):
    assert sum(cfg["scoring"]["weights"].values()) == 100


def test_similarity_same_event_vs_different():
    a = tokens("Synthetic Studio delays GTA 6 to Zeptember 2031, confirms launch window")
    b = tokens("GTA VI delayed again: now launching Zeptember 2031")
    assert similarity(a, b) >= 0.45
    assert similarity(tokens("GTA 6 Trailer 2 breakdown"), tokens("GTA 6 Trailer 3 breakdown")) < 0.45


def test_dedup_clusters_one_story_from_many_outlets(cfg, make):
    items = [
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=3),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio confirms", "tierone-b.test", hours_ago=2),
        make("GTA 6 delay: Zeptember 2031 launch confirmed", "tiertwo.test", hours_ago=1),
        make("GTA 6 fans spot flamingo statue in trailer frame", "forum.test", "community"),
    ]
    new, _, _ = normalise(items, cfg, set())
    stories, stats = cluster(new, [], cfg)
    assert len(stories) == 2
    assert max(len(s.items) for s in stories) == 3


def test_community_only_can_never_be_confirmed(cfg, make):
    new, _, _ = normalise([make("GTA 6 officially confirmed by Rockstar has confirmed hover cars",
                                "forum.test", "community")], cfg, set())
    s = Story(items=new)
    assert heuristic_label(s, cfg) in ("THEORY", "SPECULATION")
    # Even if Claude says CONFIRMED, the evidence ceiling wins. An unsourced claim is not an
    # observable find, so it cannot even reach COMMUNITY_DISCOVERY.
    assert clip("CONFIRMED", evidence(s, cfg), "SPECULATION") == "THEORY"
    # A debunk without authoritative support is not accepted
    assert clip("FALSE_OR_DEBUNKED", evidence(s, cfg), "SPECULATION") == "SPECULATION"


def test_primary_source_enables_confirmed(cfg, make):
    new, _, _ = normalise([make("GTA VI synthetic feature announced", "official.test", "primary")], cfg, set())
    assert heuristic_label(Story(items=new), cfg) == "CONFIRMED"


def test_rumour_from_tier1_is_credible_rumour_not_fact(cfg, make):
    new, _, _ = normalise([make("GTA 6 leak: insider claims synthetic DLC", "tierone-a.test")], cfg, set())
    assert heuristic_label(Story(items=new), cfg) == "CREDIBLE_RUMOUR"


def test_unhedged_hook_on_rumour_is_flagged():
    s = Story(items=[], verification_status="CREDIBLE_RUMOUR", editorial={"hook": "GTA 6 has hover cars"})
    llm.enforce_hook_hedging(s)
    assert s.editorial["hook"].startswith("[UNCONFIRMED]")


def test_end_to_end_and_72h_cooldown(cfg, make):
    batch1 = [
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=2, path="d1"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio confirms", "tierone-b.test", path="d2"),
        make("GTA 6 fans spot flamingo statue in trailer frame", "forum.test", "community", path="f1",
             engagement={"score": 4000, "comments": 600}),
    ]
    path, recs = run(cfg, use_llm=False, items_override=batch1)
    assert path.exists() and "POST NOW" in path.read_text()
    assert len(recs) == 2 and all(s.id for s, _ in recs)
    assert all(s.editorial.get("hook") and s.editorial.get("risk") for s, _ in recs)

    delay = next(s for s, _ in recs if "Zeptember" in s.headline)
    conn = connect(cfg["settings"]["database_path"])
    mark_used(conn, delay.id, "tiktok", None, None, None, None)
    conn.commit()
    conn.close()

    # Same story, only a low-tier repeat -> stays in cooldown
    _, recs2 = run(cfg, use_llm=False, items_override=[
        make("GTA 6 Zeptember 2031 delay: Synthetic Studio confirms", "tiertwo.test", path="d3")])
    assert delay.id not in [s.id for s, _ in recs2]

    # Meaningful new development (official source) -> eligible again
    _, recs3 = run(cfg, use_llm=False, items_override=[
        make("Synthetic Studio confirms GTA 6 Zeptember 2031 delay, announces launch window details",
             "official.test", "primary", hours_ago=0, path="d4")])
    again = [s for s, _ in recs3 if s.id == delay.id]
    assert again and again[0].verification_status == "CONFIRMED"


def test_claude_cannot_exceed_ceiling_or_invent_category(cfg, make, monkeypatch):
    new, _, _ = normalise([make("GTA 6 fans think the map has a synthetic island", "forum.test", "community")],
                          cfg, set())
    s = Story(items=new, verification_status="THEORY")
    fake = ('```json\n[{"id": "%d", "label": "CONFIRMED", "category": "made_up", "headline": "H", '
            '"summary": "S", "scores": {"curiosity_gap": 9}, "why_care": "w", "format": "f", '
            '"angle": "a", "hook": "The map has an island", "risk": "r", "reasoning": "x"}]\n```' % id(s))
    monkeypatch.setattr(llm, "_call", lambda *a, **k: fake)
    assert llm.editorial(cfg, [s]) == 1
    assert s.verification_status == "THEORY"                 # clipped from CONFIRMED: opinion, not a find
    assert s.content_cluster == "breaking_news"              # invalid category ignored
    assert s.dims["curiosity_gap"] == 0.9
