"""Load SYNTHETIC items for offline testing. Never used in a real run."""
import json
from datetime import datetime, timedelta, timezone

from .models import Item


def load_fixture(path: str) -> list[Item]:
    now = datetime.now(timezone.utc)
    out = []
    for d in json.load(open(path)):
        out.append(Item(url=d["url"], title=d["title"], snippet=d.get("snippet", ""),
                        publisher=d.get("publisher", ""), domain="", source_type=d["source_type"], tier=9,
                        discovered_via="fixture", published_at=now - timedelta(hours=d.get("hours_ago", 1)),
                        fetched_at=now, engagement=d.get("engagement", {}),
                        always_relevant=d.get("always_relevant", False),
                        publisher_href=d.get("publisher_href")))
    return out
