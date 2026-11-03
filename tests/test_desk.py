"""News desk: story types, the daily hot list, and how it refuses to pad."""
from research.pipeline import run


def by_headline(recs, word):
    return next(s for s, _ in recs if word in s.headline)


def test_breaking_story_tops_the_hot_list(cfg, make):
    path, recs = run(cfg, use_llm=False, items_override=[
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=2, path="a"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio says", "tierone-b.test", hours_ago=1, path="b")])
    s = recs[0][0]
    assert s.desk["bucket"] == "BREAKING" and s.desk["desk_rank"] == 1
    assert {"momentum", "recommendation_confidence", "article_suitability", "why_now"} <= set(s.desk)
    assert "significance" in s.dims and "visual_potential" not in s.dims
    text = path.read_text()
    assert "## 🔥 TOP 10 HOT STORIES" in text and "Zeptember" in text
    assert "_Only 1 stories are hot" in text            # a short list says so instead of padding
    assert "VIDEO" not in text and "MAKE NOW" not in text


def test_discovery_is_typed_and_labelled(cfg, make):
    _, recs = run(cfg, use_llm=False, items_override=[
        make("GTA 6 fans spot flamingo statue in trailer frame", "forum.test", "community", hours_ago=2)])
    s = recs[0][0]
    assert s.verification_status == "COMMUNITY_DISCOVERY" and s.desk["bucket"] == "DISCOVERY"


def test_developing_story_is_still_hot_after_a_day(cfg, make):
    _, recs = run(cfg, use_llm=False, items_override=[
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=30, path="a"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio says", "tierone-b.test", hours_ago=29, path="b")])
    assert recs and recs[0][0].desk["bucket"] == "EXPLAINER"


def test_old_stories_are_not_hot(cfg, make):
    path, recs = run(cfg, use_llm=False, items_override=[
        make("Who Lucia is: Synthetic Studio publishes GTA 6 character profile", "tierone-a.test", hours_ago=80, path="a"),
        make("Synthetic Studio publishes GTA 6 character profile explaining who Lucia is", "tierone-b.test", hours_ago=79, path="b")])
    assert recs == []
    text = path.read_text()
    assert "NO HOT STORIES RIGHT NOW." in text and "not hot: freshness" in text


def test_thin_speculation_is_skipped_not_padded(cfg, make):
    path, recs = run(cfg, use_llm=False, items_override=[
        make("GTA 6 leak: insider claims hover cars are coming", "unknown-blog.test", hours_ago=1)])
    assert recs == []
    text = path.read_text()
    assert "## 🚫 Skipped" in text and "unsupported speculation" in text


def test_hot_list_is_capped_and_the_rest_goes_on_the_radar(cfg, make):
    h = cfg["settings"]["ranking"]["hot_list"]
    h["count"], h["radar"] = 2, 1
    pairs = [("Synthetic Studio delays GTA 6 to Zeptember 2031", "GTA VI delayed to Zeptember 2031, Synthetic Studio says"),
             ("GTA 6 Quokka edition announced with plush mascot", "Quokka edition of GTA VI comes with a plush mascot"),
             ("GTA 6 marathon stream planned by Pelican Network", "Pelican Network plans a GTA VI marathon stream"),
             ("GTA 6 soundtrack includes Zorblax orchestra", "Zorblax orchestra joins the GTA VI soundtrack")]
    items = []
    for n, (a, b) in enumerate(pairs):
        items += [make(a, "tierone-a.test", hours_ago=2 + n, path=f"a{n}"), make(b, "tierone-b.test", hours_ago=1 + n, path=f"b{n}")]
    path, recs = run(cfg, use_llm=False, items_override=items)
    assert len(recs) == 2
    assert recs[0][0].rank_score >= recs[1][0].rank_score
    text = path.read_text()
    assert "## 🔥 TOP 2 HOT STORIES" in text and "## 📡 On the radar" in text
    radar = text[text.index("## 📡 On the radar"):]
    assert radar.split("\n## ")[0].count("\n- ") == 1


def _listed(cfg, headline, score, game="gta-vi"):
    from research.models import Story
    s = Story(items=[], headline=headline)
    s.rank_score, s.freshness, s.verification_status = score, 0.9, "HIGH_CONFIDENCE_REPORT"
    s.desk.update({"skip": None, "game": game})
    return s


def test_one_running_topic_cannot_fill_the_list(cfg):
    """Several stories on one topic (a firmware and jailbreak race) take at most max_per_parent_event slots."""
    from datetime import datetime, timezone
    from research.desk import hot_list
    ranked = [_listed(cfg, "Sony ships new PS5 firmware", 70), _listed(cfg, "Hackers claim a PS5 breakthrough", 69),
              _listed(cfg, "Private exploit cracks console kernel", 68), _listed(cfg, "Zorblax orchestra joins the soundtrack", 67)]
    view = hot_list(ranked, cfg, datetime.now(timezone.utc))
    assert [s.headline[:5] for s in view["hot"]] == ["Sony ", "Hacke", "Zorbl"]
    assert [s.headline[:7] for s in view["angles"]["gta-vi:console_hacking"]] == ["Private"]


def test_the_same_story_twice_gets_one_slot(cfg):
    from datetime import datetime, timezone
    from research.desk import hot_list
    ranked = [_listed(cfg, "Xbox reportedly plans three more rounds of layoffs through January", 70, "general"),
              _listed(cfg, "Xbox reportedly planning three more layoff rounds, October to January", 69, "general"),
              _listed(cfg, "Pelican Network plans a marathon stream", 60, "general")]
    view = hot_list(ranked, cfg, datetime.now(timezone.utc))
    assert len(view["hot"]) == 2 and any(k.startswith("same story: ") for k in view["angles"])
