"""Production pipeline: the parts that decide timing, captions and graphics. No network, no generation."""
from research import design, produce

PKG = {"voiceover": [{"text": "The launch has moved, a report says."}, {"text": "Nothing else changes yet. Sources are in the description."}],
       "shots": [{"seconds": 3, "vo_lines": [1], "asset_type": "AI_VIDEO"}, {"seconds": 9, "vo_lines": [2], "asset_type": "TEXT_GRAPHIC"}]}


def test_shot_lengths_come_from_the_narration_not_the_storyboard(cfg):
    c = cfg["publishing"]["video"]["production"]
    tl = produce.timeline(PKG, {1: 2.0, 2: 4.0}, cfg)
    first, second = tl["shots"]
    assert first["duration"] == round(2.0 + c["line_gap_seconds"] + c["lead_in_seconds"], 2)      # not the planned 3s
    assert second["duration"] == round(4.0 + c["line_gap_seconds"] + c["tail_seconds"], 2)        # not the planned 9s
    assert second["start"] == first["duration"] and tl["total"] == round(first["duration"] + second["duration"], 2)
    # each line is spoken inside its own shot
    assert first["lines"][0]["start"] == c["lead_in_seconds"] and second["lines"][0]["start"] == second["start"]


TL = {1: 2.0, 2: 4.0}


def styled():
    pkg = {**PKG, "hooks": ["The launch moved."], "recommended_hook": 0, "hook_title": ["THE *LAUNCH*", "JUST MOVED"],
           "end_card": {"lines": ["WORTH THE *WAIT?*"]},
           "voiceover": [{"text": "The launch has moved, a report says.", "emphasis": ["launch"]},
                         {"text": "GTA six changes nothing else yet. Sources are in the description. Worth the wait?"}],
           "shots": [{**PKG["shots"][0], "graphics": {}},
                     {**PKG["shots"][1], "graphics": {"tag": "NOT SAID", "source": {"quote": "we need more time", "by": "Studio / Outlet"}}}]}
    return pkg


def test_captions_are_short_ordered_chunks_with_few_highlights(cfg):
    pkg = styled()
    tl = produce.timeline(pkg, TL, cfg)
    caps = design.caption_chunks(pkg, tl, cfg)
    c = cfg["design"]["captions"]
    assert " ".join(x["text"] for x in caps).startswith("The launch has moved, a report says. GTA VI changes")   # spelled for the eye, not the voice
    assert all(len(x["text"]) <= c["max_chars"] + 10 for x in caps)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(caps, caps[1:]))
    hot = [w for x in caps for w, h in x["words"] if h]
    assert hot == ["launch"] and all(sum(h for _, h in x["words"]) <= c["max_highlights"] for x in caps)


def test_layout_shows_the_minimum_and_stays_inside_the_safe_areas(cfg):
    pkg = styled()
    tl = produce.timeline(pkg, TL, cfg)
    els, caps = design.layers(pkg, tl, cfg)
    d, by = cfg["design"], {}
    for e in els:
        by.setdefault(e.name.split(":")[0], []).append(e)
    W, H, safe = d["canvas"]["width"], d["canvas"]["height"], d["safe"]
    # the brand bug is small, in a corner, and there for the whole video
    bug = by["brand"][0]
    assert (bug.start, bug.end) == (0, tl["total"]) and bug.img.width < W / 3 and bug.x < W / 4 and bug.y < H / 8
    # the hook is brief, then captions take over; they never share the screen
    hook = by["hook"][0]
    assert hook.end <= d["hook"]["seconds"] and all(c.start >= hook.end for c in by["caption"])
    # no AI label on screen by default (it is in the description); when switched on it is small and brief
    assert "ai" not in by
    cfg["design"]["disclosure"]["on_screen"] = True
    shown = [e for e in design.layers(pkg, tl, cfg)[0] if e.name == "ai"]
    assert len(shown) == 1 and shown[0].end <= 3 and shown[0].img.height <= 80
    # a sourced fact can credit its source in the tag instead of naming its own state
    assert design.tag(cfg, "ON RECORD", "Game Informer").width > design.tag(cfg, "ON RECORD").width
    # an old tag name maps onto the system's states; the tag is compact and in the opposite corner
    tag = by["tag"][0]
    assert tag.name == "tag:NOT CONFIRMED" and tag.img.width < W / 3 and tag.x > W / 2 and tag.y < H / 8
    # captions sit in the lower area, above the platform UI, and clear of the right-hand buttons
    for c in by["caption"]:
        assert c.y > H / 2 and c.y + c.img.height <= H - safe["bottom"] + 40
        assert c.x >= 0 and c.x + c.img.width <= W - safe["right_lower"] + 60
    # the end card replaces captions for the closing sentence
    end = by["end"][0]
    assert end.end == tl["total"] and all(c.end <= end.start for c in by["caption"])
    # nothing covers the frame except the brief gradient under the hook and the end card
    assert all(e.img.height < H / 3 for e in els if e.name != "scrim")
    assert all(e.end <= hook.end or e.start >= end.start - 0.2 for e in by["scrim"])


def test_graphics_render_and_text_is_fully_opaque(cfg):
    pkg = styled()
    tl = produce.timeline(pkg, TL, cfg)
    els, _ = design.layers(pkg, tl, cfg)
    for e in els:
        if e.name in ("hook", "caption", "end"):
            assert e.img.getchannel("A").getextrema()[1] == 255, e.name       # never washed out
    frame = design.still(els, cfg, 3.0)
    assert frame.size == (1080, 1920) and frame.getbbox() is not None
    assert produce.speak('He said "no background" twice.') == "He said no background twice."


def test_punch_captions_sell_the_idea_and_the_transcript_stays_complete(cfg):
    pkg = styled()
    pkg.pop("hook_title")                                   # opens on the money shot: no title card
    pkg["voiceover"][0]["caption"] = "IT *MOVED*"
    pkg["voiceover"][1]["caption"] = ""                     # nothing on screen for this line
    tl = produce.timeline(pkg, TL, cfg)
    els, srt = design.layers(pkg, tl, cfg)
    caps = [e for e in els if e.name == "caption"]
    assert len(caps) == 1 and not [e for e in els if e.name == "hook"]
    assert caps[0].start <= tl["shots"][0]["lines"][0]["start"] + 0.01      # on screen with the first word
    assert caps[0].img.height > design.caption(cfg, [("it", False)]).height          # large, not reading-sized
    # the caption file for the platform is still every word that is spoken
    assert " ".join(c["text"] for c in srt).startswith("The launch has moved, a report says. GTA VI changes nothing else yet.")


def test_sound_events_are_planned_and_priced_like_any_other_generation(cfg, monkeypatch):
    monkeypatch.setattr(produce, "estimate", lambda model, params: 0.2)
    pkg = styled()
    pkg["shots"][0]["sfx"] = [{"prompt": "tyres hydroplaning, short", "at": 0.4}]
    rows = {r["key"]: r for r in produce.plan(pkg, cfg)["rows"]}
    assert rows["sfx-1-1"]["model"] == cfg["publishing"]["video"]["production"]["sfx_model"]
    assert cfg["publishing"]["video"]["production"]["mix"]["sfx_db"] < cfg["publishing"]["video"]["production"]["mix"]["voice_db"]
