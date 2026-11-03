"""Claude API web search lane.

Anti-hallucination rule: we ONLY take URLs/titles from the web_search_tool_result blocks returned
by the search tool itself. Nothing the model writes in prose becomes a source.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as dtparser

from ..models import Item

_REL = re.compile(r"(\d+)\s+(minute|hour|day|week)s?\s+ago", re.I)


def parse_page_age(s: str | None, now: datetime) -> datetime | None:
    if not s:
        return None
    m = _REL.search(s)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        return now - timedelta(**{f"{unit}s": n})
    try:
        dt = dtparser.parse(s, fuzzy=True)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None


def fetch_web_search(cfg: dict) -> tuple[list[Item], str | None]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return [], "skipped (no ANTHROPIC_API_KEY)"
    try:
        import anthropic
    except ImportError:
        return [], "skipped (anthropic package not installed)"
    ws = cfg["settings"]["discovery"]["web_search"]
    llm = cfg["settings"]["llm"]
    now = datetime.now(timezone.utc)
    prompt = (
        f"Today is {now:%A %d %B %Y} (UTC). You are a research scout for a short-form video channel about "
        "video games. Run web searches to find the NEWEST developments across gaming from the last 48 hours: "
        "official publisher and platform statements, gaming-press reports, patch consequences, and things "
        "players have discovered (hidden details, mechanics, physics, NPC behaviour, unexpected interactions). "
        "Cover PlayStation, Xbox, Nintendo, PC and the major publishers, with extra attention to Grand Theft "
        "Auto VI. Prefer recent results over evergreen pages. Run each of these queries: "
        + "; ".join(ws["queries"]) + ". Then reply with just the word DONE."
    )
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=llm["model"], max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": ws["max_searches"]}],
            messages=[{"role": "user", "content": prompt}])
    except Exception as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    out, seen = [], set()
    for block in resp.content:
        b = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        if b.get("type") != "web_search_tool_result":
            continue
        results = b.get("content")
        if not isinstance(results, list):
            continue  # error object
        for r in results:
            url, title = r.get("url"), r.get("title")
            if not url or not title or url in seen:
                continue
            seen.add(url)
            out.append(Item(url=url, title=title.strip(), snippet="", publisher="", domain="",
                            source_type="aggregator", tier=9, discovered_via="web_search",
                            published_at=parse_page_age(r.get("page_age"), now), fetched_at=now))
    return out, None
