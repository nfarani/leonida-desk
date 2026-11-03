"""NEWS DESK: story type, momentum, confidence, article suitability and the daily hot list.

Everything here is deterministic and reads thresholds from config/publishing.yaml. It decides what
KIND of opportunity a story is; it never changes a verification label or a score.
"""
from __future__ import annotations

import re
from datetime import datetime

from .models import CONFIDENCE_ORDER, Story
from .text import similarity, tokens

BUCKETS = ["BREAKING", "DISCOVERY", "EXPLAINER", "EVERGREEN"]
# Categories whose content stays useful after the news cycle moves on.
EVERGREEN_CATEGORIES = {"characters", "map", "cars", "weapons", "npc_behaviour", "police", "world_simulation",
                        "lore", "technology", "graphics", "physics", "ai_npc_systems", "game_mechanics",
                        "rockstar_history", "development_history", "radio", "music"}


def label_at_least(label: str, minimum: str) -> bool:
    """FALSE_OR_DEBUNKED needs primary or tier-1 support, so it ranks with HIGH_CONFIDENCE_REPORT."""
    if label == "FALSE_OR_DEBUNKED":
        label = "HIGH_CONFIDENCE_REPORT"
    return CONFIDENCE_ORDER.index(label) <= CONFIDENCE_ORDER.index(minimum)


def _hours(now: datetime, then: datetime) -> float:
    return max(0.0, (now - then).total_seconds() / 3600)


def _publishers(s: Story) -> set[str]:
    return {i.publisher for i in s.items if i.source_type in ("journalism", "primary")}


def _best_tier(s: Story) -> int:
    return min((i.tier for i in s.items), default=9)


def momentum(s: Story, now: datetime) -> float:
    """0-100: is coverage still arriving? Distinct publishers in the last 6h, plus existing demand."""
    recent = {i.publisher for i in s.items if _hours(now, i.when) <= 6}
    return round(100 * (0.7 * min(1.0, len(recent) / 4) + 0.3 * s.dims.get("existing_demand", 0)), 1)


def bucket_for(s: Story, cfg: dict, now: datetime) -> str:
    """The kind of story this is. Whether it makes the hot list is decided by skip_reason and hot_list."""
    b = cfg["publishing"]["buckets"]
    if s.verification_status in b["discovery"]["labels"]:
        return "DISCOVERY"
    if s.freshness >= b["breaking"]["min_freshness"]:
        return "BREAKING"
    if (s.content_cluster in EVERGREEN_CATEGORIES and _hours(now, s.event_time) >= 72
            and label_at_least(s.verification_status, b["evergreen"]["min_label"])):
        return "EVERGREEN"
    return "EXPLAINER"


def has_substance(s: Story) -> bool:
    """Enough to build 25 seconds on: a source with real text beyond its headline, or two outlets."""
    return any(len(i.snippet) > len(i.title) + 40 for i in s.items) or len(_publishers(s)) >= 2


def recommendation_confidence(s: Story, cfg: dict) -> float:
    """0-100: how far to trust this recommendation, not how good the story is. Editorial judgement
    by Claude rather than keyword priors, the strength of the label, the best source, corroboration
    and whether we hold real text. A known conflict between sources halves it."""
    tier = _best_tier(s)
    authority = 1.0 if tier <= 1 else 0.6 if tier == 2 else 0.25 if tier == 3 else 0.15
    cred = cfg["scoring"]["credibility_by_label"][s.verification_status]
    with_text = sum(1 for i in s.items if len(i.snippet) > len(i.title) + 40)
    score = (40 * (s.judged_by == "claude") + 25 * cred + 15 * authority
             + 10 * min(1.0, len(_publishers(s)) / 2) + 10 * min(1.0, with_text / 2))
    if s.editorial.get("conflict"):
        score *= 0.5
    return round(score, 1)


def article_suitability(s: Story, cfg: dict) -> float:
    """Is there enough sourced substance for an article that is more than a rewrite?"""
    pubs = _publishers(s)
    depth = min(1.0, len(pubs) / 4)
    tier = _best_tier(s)
    authority = 1.0 if tier <= 1 else 0.6 if tier == 2 else 0.25 if tier == 3 else 0.1
    cred = cfg["scoring"]["credibility_by_label"][s.verification_status]
    with_text = sum(1 for i in s.items if len(i.snippet) > len(i.title) + 40)
    substance = min(1.0, with_text / 2)
    return round(100 * (0.30 * depth + 0.30 * authority + 0.25 * cred + 0.15 * substance), 1)


# Heuristic estimates only. They rank opportunities against each other; they are not measured
# search volume or revenue, and they never touch a verification label.
_SEARCH_CATS = {"game_mechanics": 20, "characters": 15, "map": 20, "release_information": 25, "preorders": 20,
                "cars": 15, "weapons": 15, "technology": 15, "graphics": 10, "lore": 10, "police": 15,
                "world_simulation": 15, "npc_behaviour": 10, "development_history": 5}
_SEARCH_WORDS = re.compile(r"\b(how to|guide|release date|price|editions?|pre-?orders?|map|list|every|all|best|"
                           r"explained|requirements|specs|settings|file size|platforms?|patch notes|tier list)\b", re.I)
_BUY_WORDS = re.compile(r"\b(controller|headset|monitor|ssd|storage|capture card|keyboard|mouse|console|bundle|"
                        r"collector'?s|edition|pre-?orders?|price|buy|best|hardware|gpu|graphics card|handheld|"
                        r"steam deck|switch 2|ps5|xbox series|accessor(y|ies)|subscription|game pass)\b", re.I)
_UNSAFE_WORDS = re.compile(r"\b(sex|nudity|drug|cocaine|gore|decapitation|lawsuit|harass|abuse|layoffs?|"
                           r"shooting|suicide|racis|fetish)\w*", re.I)
_BASE_SEARCH = {"EVERGREEN": 65, "EXPLAINER": 50, "DISCOVERY": 35, "BREAKING": 30}


def search_score(s: Story, bucket: str) -> float:
    """0-100 estimate of search longevity: will people still look for this in a month?"""
    text = " ".join(i.title for i in s.items)
    score = _BASE_SEARCH[bucket] + _SEARCH_CATS.get(s.content_cluster, 0)
    score += 10 * min(2, len(set(m.group(0).lower() for m in _SEARCH_WORDS.finditer(text))))
    score += 5 if s.desk.get("game") else 0
    if s.verification_status in ("SPECULATION", "THEORY"):
        score -= 20          # unverified claims age badly
    return float(max(0, min(100, score)))


def commercial_score(s: Story, bucket: str) -> float:
    """0-100 estimate of commercial fit: purchase intent, longevity, advertiser safety.
    It informs planning only and never overrides an editorial or factual judgement."""
    text = " ".join(i.title for i in s.items)
    intent = min(3, len(set(m.group(0).lower() for m in _BUY_WORDS.finditer(text))))
    score = 10 + 18 * intent + 0.3 * search_score(s, bucket) + (8 if s.desk.get("flagship") else 0)
    if _UNSAFE_WORDS.search(text):
        score -= 25          # advertiser-unsafe subject matter
    if s.verification_status in ("SPECULATION", "THEORY", "CREDIBLE_RUMOUR"):
        score -= 10
    return float(max(0, min(100, round(score))))


def why_now(s: Story, d: dict, now: datetime) -> str:
    age = _hours(now, s.event_time)
    bits = [f"first reported {age:.0f}h ago" if age < 48 else f"first reported {age / 24:.0f} days ago"]
    if d["momentum"] >= 50:
        bits.append("coverage is still arriving")
    if s.saturation <= 30:
        bits.append("few outlets have it yet")
    elif s.saturation >= 65:
        bits.append("already widely covered")
    if d["bucket"] == "EXPLAINER":
        bits.append("the facts have settled, so it can be explained properly")
    return "; ".join(bits)


def skip_reason(s: Story, bucket: str, cfg: dict) -> str | None:
    """Why a story is not worth a place on the hot list, or None. Sourcing decides this, never a quota."""
    p, b = cfg["publishing"]["output"], cfg["publishing"]["buckets"]
    label, pubs, tier = s.verification_status, _publishers(s), _best_tier(s)
    if label == "SPECULATION" and p["ignore_single_source_speculation"] and (len(pubs) < 2 or tier > 2):
        return "unsupported speculation: weak sourcing, nothing verifiable to build on"
    if bucket == "BREAKING" and not label_at_least(label, b["breaking"]["min_label"]):
        return "not established enough to treat as news"
    if bucket == "DISCOVERY" and s.freshness < b["discovery"]["min_freshness"]:
        return "an old community post with no new development"
    if bucket == "EXPLAINER":
        if not label_at_least(label, b["explainer"]["min_label"]):
            return "too weakly sourced to explain as a known development"
        if len(pubs) < b["explainer"]["min_publishers"] and tier > 1:
            return "thin: one lower-tier source is not enough to explain"
    return None


# Keys from the retired video desk and from earlier runs; cleared so a stale rank is never reused.
STALE_KEYS = ("desk_rank", "tier", "tier_reason", "gate", "treatment", "video_suitability", "visual_potential",
              "hook_strength", "output", "output_reason")


def assess(s: Story, cfg: dict, now: datetime) -> dict:
    for k in STALE_KEYS:
        s.desk.pop(k, None)
    bucket = bucket_for(s, cfg, now)
    s.desk.update({"bucket": bucket, "momentum": momentum(s, now),
                   "recommendation_confidence": recommendation_confidence(s, cfg),
                   "article_suitability": article_suitability(s, cfg), "skip": skip_reason(s, bucket, cfg),
                   "search_score": search_score(s, bucket), "commercial_score": commercial_score(s, bucket)})
    s.desk["why_now"] = s.editorial.get("why_now") or why_now(s, s.desk, now)
    return s.desk


def evergreen_topics(stories: list[Story], cfg: dict, covered: set[str] = frozenset()) -> list[dict]:
    """Reference topics that the stored, well-labelled evidence can already support.
    Keywords only SELECT supporting stories; they are never a source of facts."""
    ev = cfg["publishing"]["buckets"]["evergreen"]
    out = []
    for tid, spec in cfg["evergreen"]["topics"].items():
        if tid in covered:
            continue
        pats = [re.compile(rf"\b{re.escape(k.lower())}\b") for k in spec["keywords"]]
        support = []
        for s in stories:
            if s.status == "rejected" or s.published_at is None:
                continue
            if not label_at_least(s.verification_status, ev["min_label"]):
                continue
            text = " ".join(i.title.lower() for i in s.items)
            if any(p.search(text) for p in pats):
                support.append(s)
        if len(support) < ev["min_supporting_stories"]:
            continue
        sources = {i.publisher for s in support for i in s.items if i.tier <= 2}
        confirmed = sum(1 for s in support if s.verification_status == "CONFIRMED")
        out.append({
            "topic_id": tid, "title": spec["title"], "format": spec["format"], "bucket": "EVERGREEN",
            "supporting_stories": [{"story_id": s.id, "headline": s.headline, "label": s.verification_status}
                                   for s in sorted(support, key=lambda s: s.opportunity, reverse=True)[:6]],
            "story_count": len(support), "credible_sources": len(sources), "confirmed_stories": confirmed,
            "verification": "CONFIRMED" if confirmed == len(support) else "HIGH_CONFIDENCE_REPORT",
            "output": "VIDEO_AND_ARTICLE" if len(sources) >= 3 else "ARTICLE_ONLY",
            "output_reason": (f"{len(support)} stored stories at {ev['min_label'].replace('_', ' ').lower()} or better "
                              f"from {len(sources)} credible outlets; reference value does not depend on today's news"),
            "strength": len(support) + 2 * confirmed + len(sources)})
    out.sort(key=lambda t: t["strength"], reverse=True)
    return out


_NOISE_WORDS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                "november", "december", "today", "week", "reportedly", "report", "reports", "says", "claims",
                "launch", "launching", "heading", "coming", "release", "released", "out", "now", "new", "switch",
                "steam", "pc", "game", "games", "update", "announced", "announces"]


def hot_list(ranked: list[Story], cfg: dict, now: datetime) -> dict:
    """The day's HOT LIST: the highest-ranked stories that are fresh enough and sourced well enough,
    at most `hot_list.count`, then the next `hot_list.radar` as one-liners. A ceiling, not a quota.
    One parent event (an interview, a showcase) or one running topic (a clustering concept such as
    ps5_firmware) may take at most `max_per_parent_event` slots; its other angles are listed under it
    instead of crowding out the rest of the day's news."""
    h = cfg["settings"]["ranking"]["hot_list"]
    cap = cfg["settings"]["ranking"].get("max_per_parent_event", 2)
    concepts = {c: re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)
                for c, words in h.get("topic_caps", {}).items()}

    # Words two unrelated headlines share all the time: dates, platforms, studios and news verbs
    noise = set().union(*(tokens(w) for w in cfg["settings"]["clustering"].get("generic_entities", [])),
                        *(tokens(w) for w in _NOISE_WORDS))

    def same_story(a: Story, b: Story) -> bool:
        """Clustering missed it, but it is one story: same game, similar headline, enough shared words
        that the match is not just "reportedly heading to PS5"."""
        if (a.desk.get("game") or "general") != (b.desk.get("game") or "general"):
            return False
        ta, tb = tokens(a.headline), tokens(b.headline)
        meaningful = {w for w in ta & tb if not w.isdigit() and w not in noise}
        return (len(meaningful) >= h.get("duplicate_min_shared_words", 3)
                and similarity(ta, tb) >= h.get("duplicate_similarity", 0.45))

    def events(s: Story) -> list[str]:
        """The parent event and the topic concepts (e.g. ps5_firmware) the headline belongs to. Several
        stories on one running topic are capped like angles on one interview."""
        game = s.desk.get("game") or "general"
        keys = [f"{game}:{c}" for c, rx in concepts.items() if rx.search(s.headline)]
        return ([s.desk["parent_event"]] if s.desk.get("parent_event") else []) + keys

    hot, radar, skipped, angles, seen = [], [], [], {}, {}
    for s in sorted(ranked, key=lambda s: -s.rank_score):
        d = s.desk if "skip" in s.desk else assess(s, cfg, now)
        why = d["skip"]
        if not why and s.verification_status in h["excluded_labels"]:
            why = f"label {s.verification_status.replace('_', ' ').lower()} is never on the hot list"
        if not why and s.freshness < h["min_freshness"]:
            why = f"not hot: freshness {s.freshness:.2f} (needs {h['min_freshness']})"
        if why:
            d["skip"] = why
            skipped.append(s)
            continue
        twin = next((o for o in hot + radar if same_story(o, s)), None)
        if twin:
            angles.setdefault(f"same story: {twin.headline[:60]}", []).append(s)
            continue
        keys = events(s)
        full = next((k for k in keys if seen.get(k, 0) >= cap), None)
        if full:
            angles.setdefault(full, []).append(s)
            continue
        for k in keys:
            seen[k] = seen.get(k, 0) + 1
        (hot if len(hot) < h["count"] else radar).append(s)
    radar = radar[: h["radar"]]
    for n, s in enumerate(hot, 1):
        s.desk["desk_rank"] = n
    return {"hot": hot, "radar": radar, "skipped": skipped, "angles": angles}
