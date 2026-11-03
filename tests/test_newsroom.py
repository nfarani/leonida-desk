"""Broad gaming newsroom: game tagging, scope, flagship priority, parent events, scores, video packages."""
import json

import pytest

from research import articles as A
from research import video
from research.games import detect_game
from research import higgsfield
from research.models import Story
from research.normalise import normalise
from research.pipeline import run


def general(make, title, domain="tierone-a.test", **kw):
    """An item from a general gaming feed: in scope without matching the GTA patterns."""
    it = make(title, domain, **kw)
    it.always_relevant = True
    return it


def test_game_detection_and_broad_scope(cfg, make):
    items = [general(make, "Gears of War: E-Day gets a release window", path="g1"),
             general(make, "RuneScape developers apologise for trailer", path="r1"),
             general(make, "Indie roguelike Synthetic Depths tops the charts", path="i1"),
             general(make, "Prime Day: the best controller deals this week", path="d1"),          # shopping post: out of scope
             make("A film studio announces a new drama", "tierone-b.test", path="x1")]            # not gaming, not a general feed
    new, _, stats = normalise(items, cfg, set())
    assert {i.url.rsplit("/", 1)[-1] for i in new} == {"g1", "r1", "i1"}
    assert stats["irrelevant"] == 1 and stats["not_gaming"] == 1
    by = {i.url.rsplit("/", 1)[-1]: detect_game(Story(items=[i]), cfg) for i in new}
    assert by == {"g1": "gears-of-war-e-day", "r1": "runescape", "i1": None}
    assert cfg["games"]["games"]["gta-vi"]["flagship"] is True


def test_morning_covers_general_gaming_with_flagship_priority(cfg, make):
    path, recs = run(cfg, use_llm=False, items_override=[
        general(make, "RuneScape developers apologise and pull new trailer", hours_ago=2, path="r1"),
        general(make, "RuneScape trailer pulled as developers apologise", "tierone-b.test", hours_ago=1, path="r2"),
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=2, path="g1"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio says", "tierone-b.test", hours_ago=1, path="g2")])
    games = {s.desk["game"]: s for s, _ in recs}
    assert set(games) == {"runescape", "gta-vi"}
    gta, rs = games["gta-vi"], games["runescape"]
    assert gta.desk["flagship"] and not rs.desk["flagship"] and gta.desk["franchise"] == "Grand Theft Auto"
    bonus = cfg["settings"]["ranking"]["flagship_bonus"]
    plain = gta.opportunity * (1 - cfg["settings"]["ranking"]["saturation_penalty"] * gta.saturation / 100)
    assert gta.rank_score == pytest.approx(plain + bonus, abs=0.02)
    for s in (gta, rs):
        assert 0 <= s.desk["search_score"] <= 100 and 0 <= s.desk["commercial_score"] <= 100 and s.desk["why_now"]
    text = path.read_text()
    assert "Daily Hot List" in text and "TOP 10 HOT STORIES" in text
    for col in ("Game", "Label", "Hot", "Opp", "Sig", "Fresh", "Mom", "Sat", "Published"):
        assert f"| {col} " in text
    assert "RuneScape" in text and "VIDEO" not in text
    assert [s.desk["desk_rank"] for s, _ in recs] == [1, 2] and recs[0][0] is gta   # flagship bonus puts GTA VI first
    data = json.loads(sorted(path.parent.glob("briefing_*.json"))[-1].read_text())
    assert {"game", "franchise", "search_score", "commercial_score", "momentum", "why_now"} <= set(data["recommendations"][0])


def test_commercial_score_never_changes_the_label(cfg, make):
    _, recs = run(cfg, use_llm=False, items_override=[
        general(make, "Best SSD for the new console: insider claims a cheaper bundle is coming", "unknown-blog.test", hours_ago=1, path="a"),
        general(make, "Rumour: cheaper console SSD bundle coming, insider claims", "tiertwo.test", hours_ago=1, path="b"),
        general(make, "Insider claims a cheaper SSD bundle for the new console is coming", "tierone-a.test", hours_ago=1, path="c")])
    s = recs[0][0]
    assert s.desk["commercial_score"] >= 40           # purchase intent is recognised...
    assert s.verification_status == "CREDIBLE_RUMOUR"  # ...and the rumour is still labelled a rumour


def test_one_parent_event_cannot_fill_the_briefing(cfg, make):
    # Five different angles on one interview, each carried by two outlets
    angles = [("Every pedestrian in GTA 6 has a routine, writers tell Love Magazine", "GTA 6 pedestrians follow daily routines, Love Magazine hears"),
              ("GTA 6 satire avoids naming politicians, narrative chief says in Love Magazine", "Love Magazine: GTA 6 narrative chief explains satire without politicians"),
              ("Studio spent months in wetlands researching GTA 6, Love Magazine reports", "GTA 6 wetlands research took months, according to Love Magazine"),
              ("Lucia was written to be flawed, GTA 6 writer says in Love Magazine", "Love Magazine: GTA 6 writer on making Lucia flawed"),
              ("GTA 6 radio has dozens of hosts, audio lead reveals in Love Magazine", "Love Magazine: GTA 6 audio lead describes dozens of radio hosts")]
    items = []
    for n, (t1, t2) in enumerate(angles):
        items.append(make(t1, "tierone-a.test", hours_ago=3, path=f"a{n}"))
        items.append(make(t2, "tierone-b.test", hours_ago=2, path=f"b{n}"))
    items += [general(make, "RuneScape developers apologise and pull new trailer", hours_ago=2, path="r1"),
              general(make, "RuneScape trailer pulled as developers apologise", "tierone-b.test", hours_ago=1, path="r2")]
    path, recs = run(cfg, use_llm=False, items_override=items)
    love = [s for s, _ in recs if s.desk.get("parent_event") == "gta-vi:love-magazine"]
    assert len(love) == cfg["settings"]["ranking"]["max_per_parent_event"] == 2
    assert any(s.desk["game"] == "runescape" for s, _ in recs)       # the rest of the day's news still gets in
    text = path.read_text()
    assert "More angles on stories already listed" in text


def test_feature_flags_start_safe(cfg):
    f = cfg["flags"]
    for off in ("ads_enabled", "accounts_enabled", "comments_enabled", "reactions_enabled", "auto_publish_enabled",
                "auto_video_generation_enabled", "auto_social_publish_enabled"):
        assert f[off] is False, off
    assert f["newsletter_enabled"] is True
    assert f["affiliate_enabled"] is bool(cfg["affiliates"]["products"])   # on only when real products exist
    assert cfg["publishing"]["gate"]["auto_publish"]["enabled"] is False


# ------------------------------------------------------------------ /make
def packet_and_package(cfg, make, label="HIGH_CONFIDENCE_REPORT"):
    items, _, _ = normalise([make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=3, path="s1")], cfg, set())
    packet = A.build_packet([Story(items=items, id=9, headline=items[0].title, verification_status=label)], cfg, angle_id="short")
    src = packet["sources"][0]
    c1 = A.add_claim(packet, "The studio moved the launch to Zeptember 2031.", src["id"], "stated in the report")["id"]
    c2 = A.add_claim(packet, "The studio said the time is for polish.", src["id"], "stated in the report",
                     quote="we need more time to polish the experience")["id"]
    A.save_packet(packet, cfg)
    pkg = video.new_package(9, packet, cfg, game="gta-vi", headline="delay")
    prompt = ("Vertical cinematic shot of a wall calendar whose pages flutter forward in warm afternoon light, "
              "stylised illustration, slow push-in, no readable text, no people, no brand marks.")
    hedge = "" if label == "HIGH_CONFIDENCE_REPORT" else "Reportedly, "
    pkg.update(treatment="BREAKING NEWS", editorial_angle="What the new date changes for players.",
               entertainment_angle=dict.fromkeys(video.ANGLE_KEYS, "the wait just got longer"),
               money_shot="A wall calendar tearing its own pages off.", ending_hook="wait until you hear what they cut",
               retention_edit={"cut": ["a line restating the old date"], "seconds_before": 27, "seconds_after": 20},
               viewer_test={q: {"pass": True, "note": ""} for q in cfg["publishing"]["video"]["retention"]["viewer_test"]},
               visual_premise="A calendar that will not stay still.", visual_escalation="Pages tear away faster.",
               visual_payoff="It stops on the new month.", hook_style="statement", visual_style="stylised illustration",
               hooks=[f"{hedge}the big launch just moved.", f"{hedge}there is a new date to remember.", f"{hedge}the wait got longer: here is why."],
               recommended_hook=0,
               voiceover=[{"text": "The big launch just moved.", "claims": [c1], "caption": "IT *MOVED*"},
                          {"text": "It's Zeptember now, according to a new report.", "claims": [c1], "caption": "ZEPTEMBER"},
                          {"text": "The studio says the extra time is for polish, and nothing else changes.", "claims": [c2]},
                          {"text": "So the wait got longer. But wait until you hear what they cut.", "claims": [], "kind": "framing",
                           "caption": ""}],
               shots=[{"seconds": 3, "shot_type": "wide", "camera": "push-in", "visual": "calendar", "asset_type": "AI_VIDEO",
                       "on_screen_text": "New date | AI-generated visuals, not game footage", "higgsfield_prompt": prompt, "vo_lines": [1],
                       "money_shot": True, "purpose": "pages rip away on their own: why is the date changing?"},
                      {"seconds": 5, "shot_type": "close", "camera": "static", "visual": "desk", "asset_type": "AI_IMAGE_WITH_MOTION",
                       "on_screen_text": "", "higgsfield_prompt": prompt.replace("wall calendar", "cluttered desk lamp"), "vo_lines": [2],
                       "purpose": "the new month lands"},
                      {"seconds": 6, "shot_type": "card", "camera": "none", "visual": "text card", "asset_type": "TEXT_GRAPHIC",
                       "on_screen_text": "Why: polish", "higgsfield_prompt": None, "vo_lines": [3]},
                      {"seconds": 6, "shot_type": "end card", "camera": "none", "visual": "end card", "asset_type": "TEXT_GRAPHIC",
                       "on_screen_text": "Leonida Desk", "higgsfield_prompt": None, "vo_lines": [4]}],
               editing_notes="Cut on the voice.", sound_music="Low bed.", cta="Follow for more.",
               youtube_title=f"{hedge}The launch just moved #shorts",
               youtube_description="A report says the date moved. Visuals are AI-generated illustrations, not game footage.",
               tiktok_caption="New date, per a report.", instagram_caption="New date, per a report.",
               sources=[{"name": src["publisher"], "url": src["url"]}])
    return packet, pkg


def test_make_package_passes_and_renders_every_section(cfg, make):
    packet, pkg = packet_and_package(cfg, make)
    path, issues = video.save(pkg, cfg)
    assert not [i for i in issues if i["level"] == "error"], issues
    assert pkg["status"] == "READY_FOR_GENERATION" and pkg["format"]["aspect"] == "9:16"
    lo, hi = cfg["publishing"]["video"]["seconds"]
    assert lo <= video.runtime(pkg) <= hi
    md = path.read_text()
    for section in ("Editorial angle", "What the viewer sees", "Hook options", "recommended", "Full voiceover", "Storyboard",
                    "Higgsfield prompt", "Asset type:", "Camera / motion:", "On-screen text:", "Editing notes",
                    "Sound and music", "CTA", "YouTube Shorts title", "YouTube description", "TikTok caption",
                    "Instagram caption", "Sources and evidence"):
        assert section in md, section
    # The project folder a producer works from
    d = path.parent
    for name in ("brief.md", "script.md", "storyboard.json", "higgsfield-prompts.json", "evidence.json", "social-copy.md",
                 "status.json"):
        assert (d / name).exists(), name
    assert (d / "assets").is_dir()
    assert [p["shot"] for p in json.loads((d / "higgsfield-prompts.json").read_text())] == [1, 2]
    assert json.loads((d / "status.json").read_text())["status"] == "READY_FOR_GENERATION"


def test_make_package_safeguards(cfg, make):
    def issues(mutate, label="HIGH_CONFIDENCE_REPORT", level="error"):
        packet, pkg = packet_and_package(cfg, make, label)
        mutate(pkg)
        return {i["code"] for i in video.validate(pkg, packet, cfg) if i["level"] == level}
    errors = issues

    assert errors(lambda p: None) == set()
    # A rumour inherits its label: hooks and title must be hedged, and "confirmed" is never allowed
    assert errors(lambda p: None, "CREDIBLE_RUMOUR") == set()
    assert "unhedged" in errors(lambda p: p.update(hooks=["The launch moved.", "There is a new date.", "The wait got longer."]), "CREDIBLE_RUMOUR")
    assert "rumour_upgraded" in errors(lambda p: p.update(youtube_title="Reportedly confirmed: the launch moved"), "CREDIBLE_RUMOUR")
    assert "label_upgraded" in errors(lambda p: p.update(verification_status="CONFIRMED"), "CREDIBLE_RUMOUR")
    # The voiceover cannot add facts or quotes that are not in the evidence
    assert "unsupported_claim" in errors(lambda p: p["voiceover"].append({"text": "It also adds a new island.", "claims": []}))
    assert "unsupported_quote" in errors(lambda p: p["voiceover"][0].update(text='The studio said "this will be the biggest launch ever made".'))
    assert "unknown_citation" in errors(lambda p: p["voiceover"][0].update(claims=["c99"]))
    # Unknown asset types are refused; third-party material must be a stored source with a rights note
    assert "footage" in errors(lambda p: p["shots"][0].update(asset_type="trailer_footage"))
    assert "footage" in errors(lambda p: p["shots"][0].update(asset_type="OFFICIAL_VIDEO_CLIP", asset_url="https://elsewhere.test/clip"))
    assert "rights" in issues(lambda p: p["shots"][0].update(asset_type="SCREENSHOT", asset_url=p["sources"][0]["url"],
                                                              rights_note="the report's own image, shown for comment"), level="warning")
    # No protected names in prompts, visible AI disclosure
    assert "prompt" in errors(lambda p: p["shots"][0].update(higgsfield_prompt=p["shots"][0]["higgsfield_prompt"] + " in the style of GTA 6 gameplay"))
    assert "disclosure" in errors(lambda p: p.update(youtube_description="A report says the date moved."))
    assert "disclosure" not in errors(lambda p: p["shots"][0].update(on_screen_text="New date"))   # no AI label on screen by default
    # The viewer-first fields are part of a complete package
    assert "missing" in errors(lambda p: p.update(visual_premise=""))
    # Retention problems are flagged, not silently accepted
    assert "slow_intro" in issues(lambda p: p["shots"][0].update(seconds=6), level="warning")
    assert "weak_phrase" in issues(lambda p: p["hooks"].__setitem__(0, "Did you know the big launch just moved?"), level="warning")


def test_retention_engine_refuses_videos_written_like_articles(cfg, make):
    def issues(mutate, level="error"):
        packet, pkg = packet_and_package(cfg, make)
        mutate(pkg)
        return {i["code"] for i in video.validate(pkg, packet, cfg) if i["level"] == level}
    line = lambda p, n: p["voiceover"][n]
    assert issues(lambda p: None) == set()
    # the first two seconds: no article openers, and a very short first sentence
    assert "opener" in issues(lambda p: line(p, 0).update(text="According to a new report, the launch moved."))
    assert "opener" in issues(lambda p: line(p, 0).update(text="The launch of the game that everybody has been waiting for moved again."))
    # the money shot is footage and it is shot 1
    assert "money_shot" in issues(lambda p: p["shots"][0].update(asset_type="TEXT_GRAPHIC"))
    assert "money_shot" in issues(lambda p: p["shots"][0].pop("money_shot"))
    # the story was turned into entertainment before it was scripted
    assert "angle" in issues(lambda p: p["entertainment_angle"].update(wait_what_moment=""))
    # every sentence has a visual; every generated shot says what happens in it
    assert "beat_map" in issues(lambda p: p["shots"][3].update(vo_lines=[]))
    assert "purpose" in issues(lambda p: p["shots"][0].pop("purpose"))
    # a possibility has to sound like one, however good the hook would be
    assert "speculation_as_fact" in issues(lambda p: p["voiceover"].insert(3, {"text": "The road floods.", "kind": "speculation", "claims": []})
                                           or p["shots"][2].update(vo_lines=[3, 4]) or p["shots"][3].update(vo_lines=[5]))
    assert "speculation_as_fact" not in issues(lambda p: p["voiceover"].insert(3, {"text": "Imagine the road floods.", "kind": "speculation", "claims": []})
                                               or p["shots"][2].update(vo_lines=[3, 4]) or p["shots"][3].update(vo_lines=[5]))
    # the ending opens a question, the retention edit happened, and the scroll test has no "no"
    assert "ending" in issues(lambda p: p.update(ending_hook="follow for part two"))
    assert "retention_edit" in issues(lambda p: p.update(retention_edit={"cut": []}))
    assert "viewer_test" in issues(lambda p: p["viewer_test"].pop("no_boring_second"))
    assert "viewer_test" in issues(lambda p: p["viewer_test"]["story_escalates"].update({"pass": False, "note": "flat middle"}))
    # blunt instruments, as warnings: article language, long captions, dead attention
    assert "article_style" in issues(lambda p: line(p, 2).update(text="This has significant implications for players, the studio says."), "warning")
    assert "caption" in issues(lambda p: line(p, 0).update(caption="the launch date has just been moved again"), "warning")
    assert "dead_attention" in issues(lambda p: None, "warning")          # the fixture's six-second cards are flagged


def test_videos_do_not_repeat_each_other(cfg, make):
    packet, first = packet_and_package(cfg, make)
    first["created_at"] = "2026-01-01T00:00:00+00:00"
    first["voiceover"][3]["text"] = "But here's the crazy part. But wait until you hear what they cut."
    video.save(first, cfg)
    _, second = packet_and_package(cfg, make)
    second.update(video_id=first["video_id"] + "-b", created_at="2026-01-02T00:00:00+00:00")
    second["voiceover"][3]["text"] = first["voiceover"][3]["text"]
    details = [i["detail"] for i in video.validate(second, packet, cfg) if i["code"] == "repetition"]
    assert any("rotate the style" in d for d in details) and any("crazy part" in d for d in details)


class FakeHiggsfield:
    """Stands in for the HTTP session so the job lifecycle is tested without spending anything."""
    def __init__(self):
        self.posts, self.state = [], {}

    def post(self, url, data=None, timeout=None):
        rid = f"req-{len(self.posts) + 1}"
        self.posts.append((url, json.loads(data)))
        self.state[rid] = "queued"
        return self._resp({"status": "queued", "request_id": rid, "status_url": f"https://api.test/requests/{rid}/status"})

    def get(self, url, timeout=None):
        if url.endswith("/status"):
            rid = url.split("/")[-2]
            st = self.state[rid]
            return self._resp({"status": st, **({"video": {"url": f"https://cdn.test/{rid}.mp4"}} if st == "completed" else {})})
        return self._resp({}, content=b"video-bytes")

    @staticmethod
    def _resp(data, content=b""):
        return type("R", (), {"json": lambda self: data, "raise_for_status": lambda self: None, "content": content})()


def test_render_is_manual_by_default_and_never_paid_without_confirmation(cfg, make):
    packet, pkg = packet_and_package(cfg, make)
    path, _ = video.save(pkg, cfg)
    d = path.parent
    plan = higgsfield.plan(pkg, cfg)
    assert (plan["scenes"], plan["generated_scenes"], plan["generations"]) == (4, 2, 3)   # image+motion is two generations
    assert plan["estimated_cost"] is None and "unknown" in higgsfield.plan_text(pkg, cfg)  # no price is ever guessed
    # Manual adapter: a sheet for a person, nothing sent anywhere
    assert "Nothing was sent to Higgsfield" in higgsfield.submit(pkg, d, cfg, confirm=True)
    assert (d / "generation_sheet.md").exists() and pkg["render"]["jobs"] == []
    # Clips dropped into assets/ move the package to review only when every generated shot is there
    (d / "assets" / "shot-1.mp4").write_bytes(b"x")
    assert higgsfield.ingest(pkg, d, cfg) == ([1], [2]) and pkg["status"] == "GENERATING"
    (d / "assets" / "shot-2.mp4").write_bytes(b"x")
    assert higgsfield.ingest(pkg, d, cfg) == ([1, 2], []) and pkg["status"] == "READY_FOR_REVIEW"


def test_render_api_lifecycle_persists_jobs_and_never_double_submits(cfg, make):
    hf = cfg["publishing"]["video"]["higgsfield"]
    hf["adapter"] = "api"
    packet, pkg = packet_and_package(cfg, make)
    pkg["shots"][1]["asset_type"] = "AI_VIDEO"
    path, _ = video.save(pkg, cfg)
    d = path.parent
    with pytest.raises(higgsfield.NotReady):                    # no model path configured: refuse, do not guess one
        higgsfield.submit(pkg, d, cfg, confirm=True, session=FakeHiggsfield())
    hf["models"]["text_to_video"] = {"name": "test-model", "path": "/test/model/v1", "cost_per_generation": 5,
                                     "params": {"prompt": "{prompt}", "duration": "{seconds}", "aspect_ratio": "{aspect}"}}
    fake, saves = FakeHiggsfield(), []
    assert "Nothing was submitted" in higgsfield.submit(pkg, d, cfg, session=fake) and not fake.posts   # no --confirm, no spend
    higgsfield.submit(pkg, d, cfg, confirm=True, session=fake, save=lambda p: saves.append(len(p["render"]["jobs"])))
    assert [u for u, _ in fake.posts] == ["https://api.higgsfield.ai/test/model/v1"] * 2
    assert fake.posts[0][1]["duration"] == 3 and fake.posts[0][1]["aspect_ratio"] == "9:16"
    assert saves == [1, 2] and pkg["status"] == "GENERATING" and pkg["render"]["cost"] == 10   # job ids saved after each request
    higgsfield.submit(pkg, d, cfg, confirm=True, session=fake)
    assert len(fake.posts) == 2                                 # running it again does not pay twice
    fake.state["req-1"], fake.state["req-2"] = "completed", "failed"
    higgsfield.poll(pkg, d, cfg, session=fake)
    assert (d / "assets" / "shot-1.mp4").read_bytes() == b"video-bytes" and pkg["status"] == "GENERATING"
    higgsfield.submit(pkg, d, cfg, confirm=True, session=fake)  # the failed shot is retried once
    assert len(fake.posts) == 3
    fake.state["req-3"] = "nsfw"
    higgsfield.poll(pkg, d, cfg, session=fake)
    higgsfield.submit(pkg, d, cfg, confirm=True, session=fake)  # a moderated shot is never resubmitted as is
    assert len(fake.posts) == 3 and pkg["status"] == "GENERATING"


# ------------------------------------------------------------------ relevance: no entertainment leakage
@pytest.mark.parametrize("title, path", [
    ("Lanterns season 2 reportedly in early development after season one finale", "lanterns"),
    ("What is Avatar: Seven Havens? The Last Airbender sequel explained", "avatar"),
    ("James Gunn downplays actor's Wonder Woman casting 'confirmation'", "gunn"),
    ("The Fallout TV series casts a new actor as its lead", "fallout-tv"),
    ("Sonic the Hedgehog 4 tops the box office", "sonic"),
    ("New drama about a studio", "entertainment/tv-shows/a-new-drama"),          # filed under a non-gaming section
])
def test_entertainment_coverage_does_not_enter_gaming_recommendations(cfg, make, title, path):
    new, _, stats = normalise([general(make, title, path=path)], cfg, set())
    assert new == [] and stats["not_gaming"] == 1


@pytest.mark.parametrize("title, path", [
    ("10 New Things We Just Learned About GTA 6", "ten"),
    ("Here's everything new we learned about GTA 6 this week", "roundup"),
    ("Aion 2 Factions: Best Faction to choose, Elyos or Asmodians", "guide/aion-2-factions"),
    ("Mini Review: Kingdom Hearts HD (Switch 2)", "reviews/kingdom-hearts"),
])
def test_listicles_guides_and_reviews_are_low_value(cfg, make, title, path):
    new, _, stats = normalise([general(make, title, path=path)], cfg, set())
    assert new == [] and stats["low_value"] == 1


@pytest.mark.parametrize("title", [
    "The Fallout game's next expansion adds a TV-show inspired questline",
    "Players found a hidden room in a 2023 game three years after launch",
    "Studio lays off staff after publisher cancels its next game",
    "Patch 9 quietly changed how stealth works, players say",
])
def test_real_gaming_stories_still_get_in(cfg, make, title):
    new, _, _ = normalise([general(make, title)], cfg, set())
    assert len(new) == 1


def test_stored_out_of_scope_story_is_held_back_not_recommended(cfg, make):
    """A story saved before the filter was tightened must not keep being recommended."""
    from research.normalise import story_out_of_scope
    it = general(make, "Lanterns season 2 reportedly in early development", path="lanterns-2")
    it.source_type, it.tier = "journalism", 1
    assert story_out_of_scope(Story(items=[it]), cfg) == "not_gaming"
    ok = general(make, "Studio lays off staff after publisher cancels its next game")
    ok.source_type, ok.tier = "journalism", 1
    assert story_out_of_scope(Story(items=[it, ok]), cfg) is None


def test_filler_words_do_not_cluster_unrelated_headlines():
    from research.text import similarity, tokens
    a = tokens("WE ARE COOKING - Overcooked-like chaos game, but you actually see the kitchen through the chef's eyes")
    b = tokens("Rockstar Explains How It Actually Makes A Game Like GTA 6")
    assert similarity(a, b) == 0.0


# ------------------------------------------------------------------ stored desk view and calibration
def test_performance_log_and_calibration_persist(cfg, make):
    from research import db
    from research.config import resolve
    _, recs = run(cfg, use_llm=False, items_override=[
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=2, path="a"),
        make("GTA VI delayed to Zeptember 2031, Synthetic Studio says", "tierone-b.test", hours_ago=1, path="b")])
    conn = db.connect(resolve(cfg, cfg["settings"]["database_path"]))
    sid = recs[0][0].id
    desk = json.loads(conn.execute("SELECT desk FROM stories WHERE id=?", (sid,)).fetchone()["desk"])
    assert {"desk_rank", "bucket", "momentum", "recommendation_confidence", "why_now"} <= set(desk)
    conn.execute("INSERT INTO story_ratings(story_id, rating, scores, rated_at) VALUES (?,?,?,?)", (sid, "GOOD", json.dumps(desk), "2026-10-05"))
    with pytest.raises(Exception):
        conn.execute("INSERT INTO story_ratings(story_id, rating, scores, rated_at) VALUES (?,?,?,?)", (sid, "AMAZING", "{}", "x"))
    conn.execute("""INSERT INTO video_posts(video_id, story_id, platform, published_at, treatment, hook_style, seconds)
                    VALUES ('v1', ?, 'tiktok', '2026-10-05', 'BREAKING NEWS', 'statement', 31)""", (sid,))
    conn.execute("INSERT INTO video_metrics(post_id, checkpoint, captured_at, views, avg_pct_viewed) VALUES (1, '24h', 'x', 1200, 71.5)")
    row = conn.execute("SELECT views, avg_pct_viewed FROM video_metrics m JOIN video_posts p ON p.id=m.post_id WHERE p.video_id='v1'").fetchone()
    assert (row["views"], row["avg_pct_viewed"]) == (1200, 71.5)
