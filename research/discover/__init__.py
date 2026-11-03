"""DISCOVER stage. Every fetcher returns (items, error_or_None) and never raises."""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import Item
from .reddit import fetch_reddit
from .rss import fetch_rss
from .websearch import fetch_web_search


def discover(cfg: dict, use_web_search: bool = True, log=print) -> tuple[list[Item], dict]:
    s = cfg["settings"]["discovery"]
    items: list[Item] = []
    report = {"feeds_ok": [], "feeds_failed": {}, "feeds_skipped": [], "web_search": None}
    for feed in cfg["sources"]["feeds"]:
        if not feed.get("enabled", True) or "REPLACE_WITH" in feed["url"]:
            report["feeds_skipped"].append(feed["id"])
            continue
        fetch = fetch_reddit if feed["kind"] == "reddit" else fetch_rss
        got, err = fetch(feed, s["user_agent"], s["request_timeout_seconds"])
        if err:
            report["feeds_failed"][feed["id"]] = err
            log(f"  ✗ {feed['id']}: {err}")
        else:
            report["feeds_ok"].append(feed["id"])
            log(f"  ✓ {feed['id']}: {len(got)} items")
        items.extend(got)
    if use_web_search and s["web_search"].get("enabled"):
        got, err = fetch_web_search(cfg)
        report["web_search"] = err or f"{len(got)} results"
        log(f"  {'✗' if err else '✓'} web_search: {err or f'{len(got)} results'}")
        items.extend(got)
    else:
        report["web_search"] = "disabled"
    return items, report


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
