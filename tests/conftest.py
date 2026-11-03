"""Tests use SYNTHETIC items on reserved .test domains. They never touch the network."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.config import load_config  # noqa: E402
from research.models import Item  # noqa: E402

TEST_DOMAINS = {
    "primary": {"official.test": {"name": "Official", "tier": 0}},
    "journalism": {"tierone-a.test": {"name": "Outlet A", "tier": 1},
                   "tierone-b.test": {"name": "Outlet B", "tier": 1},
                   "tiertwo.test": {"name": "Outlet C", "tier": 2}},
    "community": {"forum.test": {"name": "Forum", "tier": 4}},
}


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["sources"]["domains"] = TEST_DOMAINS
    c["settings"]["database_path"] = str(tmp_path / "t.db")
    c["settings"]["briefings_dir"] = str(tmp_path / "out")
    c["publishing"]["articles_dir"] = str(tmp_path / "articles")
    c["publishing"]["evidence_dir"] = str(tmp_path / "evidence")
    c["publishing"]["videos_dir"] = str(tmp_path / "videos")
    return c


def mk(title, domain, stype="aggregator", hours_ago=1, snippet="", engagement=None, path=None):
    now = datetime.now(timezone.utc)
    return Item(url=f"https://{domain}/{path or abs(hash(title + domain))}", title=title, snippet=snippet,
                publisher="", domain="", source_type=stype, tier=9, discovered_via="test",
                published_at=now - timedelta(hours=hours_ago), fetched_at=now, engagement=engagement or {})


@pytest.fixture
def make():
    return mk
