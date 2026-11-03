"""RANK: cooldown + saturation-adjusted ordering."""
from __future__ import annotations

from datetime import datetime, timedelta

from .community import community_types, is_community_only
from .models import Story
from .normalise import story_out_of_scope

CHATTER_REASON = "community chatter (demand signal only)"
TECH_REASON = "product and tech news: article desk only, not judged or ranked for video"


def held_back(s: Story, cfg: dict, now: datetime) -> str | None:
    cd = cfg["settings"]["cooldown"]
    if s.status == "rejected":
        return "rejected by editor"
    if s.status == "used" and s.used_at:
        within = now - s.used_at < timedelta(hours=cd["story_hours"])
        developed = s.last_material_update_at and s.last_material_update_at > s.used_at
        if within and not developed:
            hrs = cd["story_hours"] - (now - s.used_at).total_seconds() / 3600
            return f"used for content; cooldown ({hrs:.0f}h left, no meaningful new development)"
    if s.published_at is None:
        # Freshness is measured from publication. With no date on any source we cannot tell a new
        # story from a years-old page, so it is never scored as fresh.
        return "no publication date on any source (freshness unknown)"
    if is_community_only(s):
        # Discussion, questions, memes, wishlists and unclassified posts feed demand; they are not stories.
        standalone = set(cfg["settings"]["community"]["standalone_types"])
        if not standalone & set(community_types(s, cfg)):
            return CHATTER_REASON
    scope = s.desk.get("out_of_scope") or story_out_of_scope(s, cfg)
    if scope:
        return {"tech": TECH_REASON, "not_gaming": "not a gaming story (film, TV, shopping or celebrity coverage)",
                "low_value": "low-value page (listicle, roundup, guide or review): nothing new to make a story from"
                }.get(scope, scope)
    if s.freshness < 0.02:
        return "stale"
    return None


def rank(stories: list[Story], cfg: dict, now: datetime, cluster_used: dict) -> tuple[list[Story], list[Story]]:
    r, cd = cfg["settings"]["ranking"], cfg["settings"]["cooldown"]
    ranked, held = [], []
    for s in stories:
        reason = held_back(s, cfg, now)
        if reason:
            s.held_back_reason = reason
            held.append(s)
            continue
        score = s.opportunity * (1 - r["saturation_penalty"] * s.saturation / 100)
        if s.desk.get("flagship"):
            score += r.get("flagship_bonus", 0)      # extra priority for the flagship vertical
        last = cluster_used.get(s.content_cluster)
        if last and s.status != "used" and now - last < timedelta(hours=cd["topic_penalty_hours"]):
            score -= cd["topic_penalty_points"]
        s.rank_score = round(score, 2)
        ranked.append(s)
    ranked.sort(key=lambda s: s.rank_score, reverse=True)
    return ranked, held
