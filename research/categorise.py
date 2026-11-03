"""Heuristic content_cluster tagging (Claude may override in the editorial pass)."""
from __future__ import annotations

from .models import Story


def categorise(s: Story, cfg: dict) -> str:
    if s.verification_status == "FALSE_OR_DEBUNKED":
        return "debunking"
    text = " " + " ".join(f"{i.title} {i.snippet[:200]}" for i in s.items).lower() + " "
    best, best_hits = cfg["categories"]["default_category"], 0
    for slug, spec in cfg["categories"]["categories"].items():
        hits = sum(text.count(k) for k in spec["keywords"])
        if hits > best_hits:
            best, best_hits = slug, hits
    if s.verification_status in ("CREDIBLE_RUMOUR", "SPECULATION") and best in ("breaking_news",):
        return "rumours"
    if s.verification_status == "THEORY" and best == "breaking_news":
        return "community_theories"
    return best
