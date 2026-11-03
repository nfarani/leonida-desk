"""Reddit listing JSON (with RSS fallback). Community items are LEADS, never facts."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Item
from ..text import strip_html
from .rss import fetch_rss


def fetch_reddit(feed: dict, user_agent: str, timeout: int) -> tuple[list[Item], str | None]:
    try:
        r = requests.get(feed["url"], headers={"User-Agent": user_agent}, timeout=timeout)
        r.raise_for_status()
        children = r.json()["data"]["children"]
    except Exception as exc:  # 403/429 are common for unauthenticated JSON -> try RSS
        rss_feed = {**feed, "url": feed["url"].replace(".json", ".rss")}
        items, err = fetch_rss(rss_feed, user_agent, timeout)
        if err:
            return [], f"json failed ({type(exc).__name__}); rss fallback failed ({err})"
        for it in items:
            it.publisher = "Reddit"
        return items, None
    now = datetime.now(timezone.utc)
    out = []
    for c in children:
        d = c.get("data", {})
        if d.get("stickied") or not d.get("permalink"):
            continue
        flair = d.get("link_flair_text") or ""
        snippet = strip_html(d.get("selftext"), 500)
        if d.get("url") and not d.get("is_self"):
            snippet = f"[links to {d['url']}] {snippet}".strip()
        out.append(Item(
            url="https://www.reddit.com" + d["permalink"], title=strip_html(d.get("title"), 300),
            snippet=(f"[flair: {flair}] " if flair else "") + snippet, publisher="Reddit",
            domain="reddit.com", source_type="community", tier=4, discovered_via=feed["id"],
            published_at=datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc),
            fetched_at=now, always_relevant=feed.get("always_relevant", False),
            engagement={"score": d.get("score", 0), "comments": d.get("num_comments", 0),
                        "upvote_ratio": d.get("upvote_ratio")}))
    return out, None
