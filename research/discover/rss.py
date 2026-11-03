"""RSS/Atom feeds, including Google News search feeds (aggregator)."""
from __future__ import annotations

import calendar
from datetime import datetime, timezone

import feedparser
import requests

from ..models import Item
from ..text import strip_html, strip_publisher_suffix


def _ts(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def parse_feed_bytes(content: bytes, feed: dict) -> list[Item]:
    parsed = feedparser.parse(content)
    now = datetime.now(timezone.utc)
    out = []
    for e in parsed.entries:
        link = e.get("link")
        title = e.get("title")
        if not link or not title:
            continue
        src = e.get("source") or {}
        publisher = src.get("title") if isinstance(src, dict) else None
        href = src.get("href") if isinstance(src, dict) else None
        out.append(Item(
            url=link, title=strip_publisher_suffix(strip_html(title, 300), publisher),
            snippet=strip_html(e.get("summary"), 600), publisher=publisher or feed["name"],
            domain="", source_type=feed["source_type"], tier=9, discovered_via=feed["id"],
            published_at=_ts(e), fetched_at=now, always_relevant=feed.get("always_relevant", False),
            publisher_href=href))
    return out


def fetch_rss(feed: dict, user_agent: str, timeout: int) -> tuple[list[Item], str | None]:
    try:
        r = requests.get(feed["url"], headers={"User-Agent": user_agent}, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    items = parse_feed_bytes(r.content, feed)
    if not items:
        return [], "feed returned 0 parseable entries"
    return items, None
