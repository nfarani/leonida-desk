"""In-memory data structures passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

LABELS = ["CONFIRMED", "HIGH_CONFIDENCE_REPORT", "CREDIBLE_RUMOUR", "COMMUNITY_DISCOVERY",
          "THEORY", "SPECULATION", "FALSE_OR_DEBUNKED"]
CONFIDENCE_ORDER = LABELS[:-1]  # FALSE_OR_DEBUNKED is handled separately


@dataclass
class Item:
    """One article / post / video / search result."""
    url: str
    title: str
    snippet: str
    publisher: str
    domain: str
    source_type: str          # primary | journalism | community
    tier: int                 # 0 official ... 4 community
    discovered_via: str       # feed id or 'web_search'
    published_at: datetime | None
    fetched_at: datetime
    engagement: dict = field(default_factory=dict)
    always_relevant: bool = False
    publisher_href: str | None = None   # aggregator feeds: real publisher site
    content_type: str = ""              # community items only, see community.py

    @property
    def when(self) -> datetime:
        return self.published_at or self.fetched_at


@dataclass
class Story:
    """One underlying event, possibly reported by many items."""
    items: list[Item]
    id: int | None = None
    headline: str = ""
    summary: str = ""
    first_seen_at: datetime | None = None
    last_updated_at: datetime | None = None
    last_material_update_at: datetime | None = None
    verification_status: str = "SPECULATION"
    previous_status: str | None = None
    content_cluster: str = "breaking_news"
    status: str = "new"
    used_at: datetime | None = None
    new_items: list[Item] = field(default_factory=list)
    # scoring
    dims: dict = field(default_factory=dict)       # dimension -> 0..1
    freshness: float = 0.0
    viral: float = 0.0
    saturation: float = 0.0
    opportunity: float = 0.0
    rank_score: float = 0.0
    reasoning: str = ""
    editorial: dict = field(default_factory=dict)  # why_care, format, angle, hook, risk
    held_back_reason: str | None = None
    judged_by: str = "heuristic"
    absorbed: list["Story"] = field(default_factory=list)   # duplicate stories merged into this one
    desk: dict = field(default_factory=dict)       # bucket, momentum, suitability, output (desk.py)

    @property
    def published_at(self) -> datetime | None:
        dates = [i.published_at for i in self.items if i.published_at]
        return min(dates) if dates else None

    @property
    def event_time(self) -> datetime:
        return self.published_at or self.first_seen_at or min(i.fetched_at for i in self.items)

    def best_item(self) -> Item:
        """Most authoritative, then earliest."""
        return sorted(self.items, key=lambda i: (i.tier, i.when))[0]

    def publishers(self) -> set[str]:
        return {i.publisher for i in self.items}
