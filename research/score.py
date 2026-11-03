"""SCORE: freshness, demand, novelty, credibility (computed) + judged dims, viral, saturation."""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

from .models import Story
from .text import similarity, tokens

# Category priors for judged dimensions when Claude is unavailable (0-1).
PRIORS = {
    "trailer_discoveries": dict(curiosity_gap=.75, surprise=.6, emotional_reaction=.6),
    "hidden_details": dict(curiosity_gap=.8, surprise=.65),
    "easter_eggs": dict(curiosity_gap=.75, surprise=.65, shareability=.65),
    "map": dict(curiosity_gap=.7, comment_potential=.6),
    "release_information": dict(emotional_reaction=.8, comment_potential=.7, shareability=.6, significance=.75),
    "rockstar_announcements": dict(surprise=.6, emotional_reaction=.7, shareability=.6, significance=.75),
    "breaking_news": dict(surprise=.55, emotional_reaction=.55, significance=.6),
    "rumours": dict(curiosity_gap=.7, comment_potential=.75, emotional_reaction=.55),
    "community_theories": dict(curiosity_gap=.7, comment_potential=.8),
    "debunking": dict(curiosity_gap=.6, shareability=.6, comment_potential=.6),
    "controversies": dict(emotional_reaction=.75, comment_potential=.8, significance=.6),
    "memes": dict(shareability=.85, emotional_reaction=.6),
    "sales": dict(surprise=.4, significance=.6), "records": dict(surprise=.55, shareability=.65),
    "characters": dict(curiosity_gap=.6, emotional_reaction=.6),
}
BOOSTS = {
    "curiosity_gap": ["hidden", "secret", "missed", "why", "revealed", "mystery", "?", "spotted"],
    "surprise": ["unexpected", "surprise", "first time", "never", "shock", "finally"],
    "emotional_reaction": ["delay", "price", "$", "angry", "backlash", "love", "insane", "worried"],
    "shareability": ["meme", "funny", "record", "most"],
    "comment_potential": ["theory", "rumour", "rumor", "leak", "debate", "price", "should"],
    "significance": ["announce", "announced", "release date", "delay", "price", "layoffs", "acquire", "acquisition",
                     "shut", "closing", "cancelled", "canceled", "official", "confirmed", "sales", "record"],
}


def hours_between(a: datetime, b: datetime) -> float:
    return max(0.0, (a - b).total_seconds() / 3600)


def freshness(s: Story, cfg: dict, now: datetime) -> float:
    f = cfg["settings"]["freshness"]
    hl = f["half_life_hours"]
    base = 0.5 ** (hours_between(now, s.event_time) / hl)
    if s.last_material_update_at and hours_between(now, s.last_material_update_at) <= f["update_bump_hours"]:
        base = max(base, 0.85 * 0.5 ** (hours_between(now, s.last_material_update_at) / hl))
    return round(base, 4)


def demand(s: Story, now: datetime) -> float:
    eng = sum(i.engagement.get("score", 0) + 2 * i.engagement.get("comments", 0) for i in s.items)
    eng_n = min(1.0, math.log10(1 + max(0, eng)) / math.log10(1 + 5000))
    recent_pubs = {i.publisher for i in s.items if hours_between(now, i.when) <= 24}
    vel_n = min(1.0, len(recent_pubs) / 6)
    return round(1 - (1 - eng_n) * (1 - vel_n), 4)


def novelty(s: Story, used: list[tuple[int, set[str]]]) -> float:
    toks = tokens(s.headline)
    sims = [similarity(toks, t) for sid, t in used if sid != s.id]
    return round(1 - max(sims, default=0.0), 4)


def heuristic_judged(s: Story) -> None:
    text = " ".join(i.title.lower() for i in s.items)
    prior = PRIORS.get(s.content_cluster, {})
    for dim, words in BOOSTS.items():
        if dim in s.dims:
            continue
        v = prior.get(dim, 0.4) + 0.08 * sum(w in text for w in words)
        s.dims[dim] = round(min(1.0, v), 3)


def preliminary(s: Story, cfg: dict) -> float:
    """Opportunity on keyword priors alone, without touching the story. Only used to decide which
    stories are worth sending to Claude first."""
    probe = Story(items=s.items, content_cluster=s.content_cluster, dims=dict(s.dims))
    heuristic_judged(probe)
    weights = cfg["scoring"]["weights"]
    return sum(weights[d] * probe.dims.get(d, 0) for d in weights)


def youtube_competitor_count(query: str, cfg: dict) -> int | None:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return None
    try:
        import requests
        after = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=15, params={
            "key": key, "q": query, "part": "id", "type": "video", "publishedAfter": after, "maxResults": 50})
        r.raise_for_status()
        return len(r.json().get("items", []))
    except Exception:
        return None


def saturation(s: Story, cfg: dict, now: datetime, yt_count: int | None) -> float:
    c = cfg["scoring"]["saturation"]
    w = dict(c["weights"])
    outlets = {i.publisher for i in s.items if i.source_type in ("journalism", "primary")}
    parts = {"outlets": min(1.0, len(outlets) / c["outlet_count_full"]),
             "age": min(1.0, hours_between(now, s.event_time) / c["age_full_hours"])}
    if yt_count is not None:
        parts["youtube"] = min(1.0, yt_count / c["youtube_videos_full"])
    else:
        w.pop("youtube", None)
    total_w = sum(w.values())
    return round(100 * sum(parts[k] * w[k] for k in parts) / total_w, 2)


def compute_deterministic(s: Story, cfg: dict, now: datetime, used) -> None:
    s.freshness = freshness(s, cfg, now)
    s.dims["freshness"] = s.freshness
    s.dims["existing_demand"] = demand(s, now)
    s.dims["novelty"] = novelty(s, used)
    s.dims["credibility"] = cfg["scoring"]["credibility_by_label"][s.verification_status]


def finalise(s: Story, cfg: dict, now: datetime, check_youtube: bool = False) -> None:
    heuristic_judged(s)  # fills any judged dims Claude did not supply
    s.dims["credibility"] = cfg["scoring"]["credibility_by_label"][s.verification_status]
    weights = cfg["scoring"]["weights"]
    s.opportunity = round(sum(weights[d] * s.dims.get(d, 0) for d in weights), 2)
    vc = cfg["scoring"]["viral_components"]
    s.viral = round(100 * sum(vc[d] * s.dims.get(d, 0) for d in vc) / sum(vc.values()), 2)
    yt = youtube_competitor_count(f"GTA 6 {s.headline}", cfg) if check_youtube else None
    s.saturation = saturation(s, cfg, now, yt)
