"""NORMALISE: canonical URLs, publisher classification, relevance + age filters, URL dedup."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .models import Item
from .text import canonical_url, domain_of

DEFAULT_TIER = {"primary": 0, "journalism": 3, "community": 4}


def classify_domain(domain: str, registry: dict) -> tuple[str, str, int] | None:
    """Return (source_type, name, tier) for the most specific matching registered domain."""
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        for stype, entries in registry.items():
            if cand in entries:
                e = entries[cand]
                return stype, e["name"], e["tier"]
    return None


def _apply_classification(it: Item, registry: dict) -> None:
    # Aggregators (Google News, web search) are re-classified by the real publisher.
    lookup_domain = domain_of(it.publisher_href) if it.publisher_href else domain_of(it.url)
    it.domain = lookup_domain
    hit = classify_domain(lookup_domain, registry)
    feed_type = it.source_type
    if hit:
        stype, name, tier = hit
        # A feed explicitly declared primary (e.g. Rockstar's own YouTube channel) stays primary
        # even though youtube.com in general is community.
        if feed_type == "primary":
            stype, tier = "primary", 0
        it.source_type, it.tier = stype, tier
        # Google News spells outlets its own way ("Polygon.com", "Video Games Chronicle"); one outlet
        # must count once, so a registered domain always takes the registry name.
        if not it.publisher or it.publisher in ("Reddit",) or it.discovered_via == "web_search" \
                or feed_type == "aggregator":
            it.publisher = name
    else:
        if feed_type == "aggregator":
            it.source_type, it.tier = "journalism", 3   # unknown publisher: low tier, never CONFIRMED alone
        else:
            it.tier = DEFAULT_TIER.get(feed_type, 3) if it.tier == 9 else it.tier
        if not it.publisher:
            it.publisher = lookup_domain or "unknown"


def _out_of_scope(it: Item, tracked, excluded, entertainment, ent_primary, low_value, gaming, sections,
                  low_sections=None) -> str | None:
    """Why a press item is not a gaming story worth clustering, or None if it is in scope.
    A franchise name alone does not make a film, TV or shopping piece a gaming story."""
    title = it.title
    path = urlsplit(it.publisher_href or it.url).path if it.publisher_href or "news.google.com" not in it.url else ""
    if sections and path and sections.search(path):
        return "not_gaming"
    if any(p.search(title) for p in excluded):
        return "not_gaming"
    if any(p.search(title) for p in ent_primary):
        return "not_gaming"
    about_game = bool(gaming and gaming.search(title)) or any(p.search(title) for p in tracked)
    if any(p.search(title) for p in entertainment) and not about_game:
        return "not_gaming"
    if any(p.search(title) for p in low_value) or (low_sections and path and low_sections.search(path)):
        return "low_value"
    return None


_scope_cache: dict[int, tuple] = {}

TECH = "tech"


def lane_of(it: Item, cfg: dict) -> str:
    """The lane of the feed an item came from ("" = gaming). Product and tech news is its own lane."""
    lanes = cfg.setdefault("_lanes", {f["id"]: f.get("lane", "") for f in cfg["sources"].get("feeds", [])})
    return lanes.get(it.discovered_via, "")


def _tech_low_value(it: Item, cfg: dict) -> bool:
    """Shopping posts, listicles, guides and reviews are no more a story in tech than in gaming."""
    rel = cfg["settings"]["relevance"]
    pats = [re.compile(p, re.I) for p in rel.get("exclude_patterns", []) + rel.get("low_value_patterns", [])]
    return any(p.search(it.title) for p in pats)


def scope_check(cfg: dict):
    """(tracked patterns, check). check(item) says why a press item is out of scope, or None."""
    rel = cfg["settings"]["relevance"]
    if id(rel) not in _scope_cache:
        patterns = [re.compile(p, re.I) for p in rel["patterns"]]
        comp = lambda key: [re.compile(p, re.I) for p in rel.get(key, [])]
        excluded, entertainment, ent_primary, low_value = (comp("exclude_patterns"), comp("entertainment_patterns"),
                                                           comp("entertainment_primary"), comp("low_value_patterns"))
        gaming = re.compile(rel["gaming_signals"], re.I) if rel.get("gaming_signals") else None
        sections = re.compile(r"/(" + "|".join(map(re.escape, rel.get("exclude_url_sections", []))) + r")(/|$)", re.I) \
            if rel.get("exclude_url_sections") else None
        low_sections = re.compile(r"/(" + "|".join(map(re.escape, rel.get("low_value_url_sections", []))) + r")(/|$)", re.I) \
            if rel.get("low_value_url_sections") else None
        _scope_cache[id(rel)] = (patterns, lambda it: _out_of_scope(it, patterns, excluded, entertainment, ent_primary,
                                                                    low_value, gaming, sections, low_sections))
    return _scope_cache[id(rel)]


def story_out_of_scope(story, cfg: dict) -> str | None:
    """A stored story is out of scope when every press item in it is. Stories saved before a filter
    was tightened are caught here instead of staying in the recommendations."""
    press = [i for i in story.items if i.source_type != "community"]
    if not press:
        return None
    if all(lane_of(i, cfg) == TECH for i in press):
        return TECH        # article desk only; a tech item attached to a gaming story is just a source
    _, check = scope_check(cfg)
    reasons = [check(i) for i in press]
    return reasons[0] if all(reasons) else None


def normalise(items: list[Item], cfg: dict, known: set[str]) -> tuple[list[Item], list[Item], dict]:
    """Returns (new_items, already_known_items, stats)."""
    registry = cfg["sources"]["domains"]
    patterns, check = scope_check(cfg)
    max_age = timedelta(hours=cfg["settings"]["discovery"]["max_item_age_hours"])
    now = datetime.now(timezone.utc)
    stats = {"raw": len(items), "irrelevant": 0, "too_old": 0, "dup_url": 0, "known": 0,
             "not_gaming": 0, "low_value": 0}
    seen: set[str] = set()
    new, old = [], []
    for it in items:
        it.url = canonical_url(it.url)
        if it.url in seen:
            stats["dup_url"] += 1
            continue
        seen.add(it.url)
        text = f"{it.title} {it.snippet}"
        if not it.always_relevant and not any(p.search(text) for p in patterns):
            stats["irrelevant"] += 1
            continue
        if lane_of(it, cfg) == TECH:
            if _tech_low_value(it, cfg):
                stats["low_value"] += 1
                continue
        elif it.source_type != "community":
            reason = check(it)
            if reason:
                stats[reason] += 1
                continue
        if it.published_at and now - it.published_at > max_age:
            stats["too_old"] += 1
            continue
        if not it.published_at and it.discovered_via == "web_search":
            # undated search results are usually evergreen pages; never score them as fresh
            stats["too_old"] += 1
            continue
        _apply_classification(it, registry)
        if it.url in known:
            stats["known"] += 1
            old.append(it)
            continue
        new.append(it)
    stats["new"] = len(new)
    return new, old, stats
