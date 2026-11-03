"""Game tagging and parent events.

A story is tagged with a game from config/games.yaml when a registered alias appears in one of its
headlines. A parent event groups stories that are different angles on one interview, cover story or
showcase, so a single event cannot fill the whole briefing. Both are derived from stored text only.
"""
from __future__ import annotations

import re
from .models import Story

_cache: dict[int, list] = {}


def _aliases(cfg: dict) -> list[tuple[re.Pattern, str]]:
    key = id(cfg["games"])
    if key not in _cache:
        pats = []
        for slug, g in cfg["games"]["games"].items():
            for a in sorted(g.get("aliases") or [], key=len, reverse=True):
                pats.append((re.compile(rf"(?<![a-z0-9]){re.escape(a.lower())}(?![a-z0-9])"), slug))
        _cache[key] = pats
    return _cache[key]


GTA_FEEDS = ("gn_gta6", "gn_rockstar", "gn_take_two", "reddit_gta6", "gtaforums")


def detect_game(story: Story, cfg: dict) -> str | None:
    """Slug of the registered game most often named in the story's headlines, or None.
    Items from the GTA-only feeds count as GTA VI even when the headline does not name the game."""
    hits: dict[str, int] = {}
    for it in story.items:
        low = it.title.lower().replace("’", "'")
        slug = next((sl for pat, sl in _aliases(cfg) if pat.search(low)), None)
        if slug is None and it.discovered_via.startswith(GTA_FEEDS):
            slug = "gta-vi"
        if slug:
            hits[slug] = hits.get(slug, 0) + 1
    return max(hits, key=hits.get) if hits else None


def detect_origin(story: Story, cfg: dict) -> str | None:
    """The publication or event several outlets are relaying, if the story's text names one."""
    text = " ".join(f"{i.title} {i.snippet[:300]}" for i in story.items).lower()
    for origin, names in cfg["settings"]["parent_events"]["origins"].items():
        if any(re.search(rf"\b{re.escape(n)}\b", text) for n in names):
            return origin
    return None


def tag(story: Story, cfg: dict) -> None:
    slug = detect_game(story, cfg)
    game = cfg["games"]["games"].get(slug) if slug else None
    origin = detect_origin(story, cfg)
    story.desk.update({
        "game": slug, "game_name": (game.get("short_name") or game["name"]) if game else story.desk.get("game_name"),
        "franchise": game.get("franchise") if game else None,
        "flagship": bool(game and game.get("flagship")),
        # Claude may replace this with a more precise key when it can see several stories at once
        "parent_event": f"{slug or 'general'}:{origin}" if origin else story.desk.get("parent_event")})
