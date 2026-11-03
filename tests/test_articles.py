"""Evidence-first articles: packets, fact checks, scores, the publication gate and the site build."""
import shutil
import subprocess
from datetime import timedelta

import pytest

from research import articles as A
from research.config import ROOT
from research.deploy import VercelAdapter, deploy_if_enabled
from research.models import Story
from research.normalise import normalise

FACTS = [
    ("Synthetic Studio said GTA 6 will launch in Zeptember 2031.", "Launch window stated in the post."),
    ("The studio said the extra time is for polish.", "Reason given in the post."),
    ("Pre-orders already placed stay valid.", "Stated in the post's FAQ."),
    ("The delay applies to every platform.", "Stated in the post."),
]


def story(cfg, make, specs, label):
    items, _, _ = normalise([make(t, d, st, hours_ago=h, path=f"p{n}") for n, (t, d, st, h) in enumerate(specs)], cfg, set())
    s = Story(items=items, id=7, headline=items[0].title, verification_status=label)
    return s


def good_article(cfg, make, label="HIGH_CONFIDENCE_REPORT", specs=None, slug="gta-6-delay-explained", angle_id="delay"):
    specs = specs or [("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", "aggregator", 5),
                      ("GTA VI delayed to Zeptember 2031, studio says", "tierone-b.test", "aggregator", 4)]
    p = A.build_packet([story(cfg, make, specs, label)], cfg, angle="What the delay changes", angle_id=angle_id,
                       bucket="BREAKING")
    for s in p["sources"]:
        s["opened"] = True
    ids = [A.add_claim(p, c, p["sources"][n % len(p["sources"])]["id"], e)["id"] for n, (c, e) in enumerate(FACTS)]
    body = f"""The studio has moved the game's launch to Zeptember of that year.[^{ids[0]}]

## What changed

The company put the extra time down to polish.[^{ids[1]}] Existing pre-orders are unaffected.[^{ids[2]}]

- Every platform moves together.[^{ids[3]}]

## Why it matters

A later date mostly affects planning for players who booked time off. It also leaves the surrounding
season open for other releases, which is where the interesting consequences are likely to show up.

## What we don't know

We do not know whether the new date is final. Treat it as the current plan and nothing more.
"""
    meta = dict(story_id=7, parent_event_id=None, angle_id=angle_id, title="GTA 6 delay: what actually changes for players",
                slug=slug, description="The studio has moved GTA 6. What was said, what stays the same and what is still open.",
                hero_media=None, author=cfg["publishing"]["publication"]["byline"], editorial_bucket="BREAKING",
                verification_status=label, tags=["release"], related_content=[], status="DRAFT")
    return meta, body, p


def test_evidence_packet_generation(cfg, make):
    s = story(cfg, make, [("Synthetic Studio confirms GTA 6 delay", "official.test", "primary", 3),
                          ("GTA 6 delayed, studio says", "tiertwo.test", "aggregator", 2),
                          ("GTA 6 fans spot new date on trailer thumbnail", "forum.test", "community", 1)], "CONFIRMED")
    p = A.build_packet([s], cfg, angle="x", angle_id="delay")
    assert len(p["sources"]) == 3 and all(c["kind"] == "headline" for c in p["claims"])
    assert all({"claim", "source_id", "source_url", "source_date", "verification", "evidence"} <= set(c) for c in p["claims"])
    levels = {src["source_type"]: c["verification"] for src, c in zip(p["sources"], p["claims"])}
    assert levels["primary"] == "CONFIRMED" and levels["journalism"] == "CREDIBLE_RUMOUR" and levels["community"] == "THEORY"
    forum = next(x["id"] for x in p["sources"] if x["source_type"] == "community")
    # A writer can lower a claim's level but never lift it above what its source supports
    assert A.add_claim(p, "The date is final.", forum, "poster's reading", verification="CONFIRMED")["verification"] == "THEORY"
    path = A.save_packet(p, cfg)
    assert A.load_packet(p["packet_id"], cfg)["story_label"] == "CONFIRMED" and path.exists()


def test_unsupported_claim_detection(cfg, make):
    meta, body, p = good_article(cfg, make)
    assert not [i for i in A.fact_check(meta, body, p, cfg) if i["level"] == "error"]
    bad = body.replace("## What changed", "The studio also promised a free expansion for everyone who waited.\n\n## What changed")
    bad += '\n\nA spokesperson said: "We are sorry and we will make it up to every single player".[^c5]\n'
    bad += "\n\nThe new map is twice the size.[^c99]\n"
    codes = {i["code"] for i in A.fact_check(meta, bad, p, cfg)}
    assert {"unsupported_claim", "unsupported_quote", "unknown_citation"} <= codes
    # Analysis may interpret, but may not smuggle in a number or an attribution
    sneaky = body.replace("We do not know whether the new date is final.", "Insiders said it will slip another 6 months.")
    assert any(i["code"] == "unsupported_claim" for i in A.fact_check(meta, sneaky, p, cfg))
    report = A.evaluate(meta, bad, p, cfg)
    assert report["gate"] == "DO_NOT_PUBLISH"


def test_rumour_wording_cannot_be_upgraded(cfg, make):
    meta, body, p = good_article(cfg, make, label="CREDIBLE_RUMOUR")
    meta["title"] = "GTA 6 delay officially confirmed: what changes for players"
    assert any(i["code"] == "rumour_upgraded" for i in A.fact_check(meta, body, p, cfg))
    meta2, body2, p2 = good_article(cfg, make, label="CREDIBLE_RUMOUR")
    meta2["verification_status"] = "CONFIRMED"
    assert any(i["code"] == "label_upgraded" for i in A.fact_check(meta2, body2, p2, cfg))


def test_thin_story_rejection(cfg, make):
    meta, body, p = good_article(cfg, make)
    thin = body.split("## What changed")[0] + "\n## Why it matters\n\nIt changes plans.\n"
    report = A.evaluate(meta, thin, p, cfg)
    assert report["gate"] == "DO_NOT_PUBLISH" and any("thin story" in r for r in report["gate_reasons"])


def test_originality_gate_blocks_a_rewrite(cfg, make):
    meta, body, p = good_article(cfg, make)
    assert A.originality_score(body, p, cfg) >= 70
    copied = "\n\n".join(f"{s['title']}.[^{c['id']}]"
                         for s, c in zip(p["sources"] * 3, [c for c in p["claims"] if c["kind"] == "fact"]))
    report = A.evaluate(meta, copied, p, cfg)
    assert report["source_overlap"] >= cfg["publishing"]["article"]["rewrite_overlap"]
    assert report["originality_score"] <= 30 and report["gate"] == "DO_NOT_PUBLISH"
    assert any("rewrite" in r for r in report["gate_reasons"])


def test_duplicate_article_rejection(cfg, make):
    meta, body, p = good_article(cfg, make)
    A.save_article(meta, body, p, cfg)
    meta2, body2, p2 = good_article(cfg, make, slug="gta-6-delay-again")
    meta2["title"] = "GTA 6 has a new date: the practical consequences"
    path, report = A.save_article(meta2, body2, p2, cfg)
    assert report["duplicates"] == ["gta-6-delay-explained"] and report["gate"] == "DO_NOT_PUBLISH"
    assert A.parse(path.read_text())[0]["status"] == "DRAFT"


def test_rumour_requires_review(cfg, make):
    # Conflicting reports need an editor even when the label is strong
    meta, body, p = good_article(cfg, make)
    p["conflicts"].append({"description": "outlets give different months", "resolved": False})
    report = A.evaluate(meta, body, p, cfg)
    assert report["gate"] == "REVIEW_REQUIRED" and any("disagree" in r for r in report["gate_reasons"])
    # A credible rumour always does, however well written
    meta, body, p = good_article(cfg, make, label="CREDIBLE_RUMOUR")
    path, report = A.save_article(meta, body, p, cfg)
    assert report["gate"] == "REVIEW_REQUIRED" and any("credible rumour" in r for r in report["gate_reasons"])
    assert A.parse(path.read_text())[0]["status"] == "REVIEW_REQUIRED"


def test_primary_sourced_article_can_be_auto_publish_eligible_but_is_not_published(cfg, make):
    specs = [("Synthetic Studio confirms GTA 6 moves to Zeptember 2031", "official.test", "primary", 3),
             ("GTA 6 delayed to Zeptember 2031, studio says", "tierone-a.test", "aggregator", 2),
             ("Studio explains GTA 6 delay to Zeptember 2031", "tierone-b.test", "aggregator", 2)]
    meta, body, p = good_article(cfg, make, label="CONFIRMED", specs=specs)
    path, report = A.save_article(meta, body, p, cfg)
    assert report["gate"] == "AUTO_PUBLISH_ELIGIBLE", report
    saved = A.parse(path.read_text())[0]
    # The master switch is off: eligible still means a human approves, and nothing is published
    assert cfg["publishing"]["gate"]["auto_publish"]["enabled"] is False
    assert saved["status"] == "REVIEW_REQUIRED" and saved["published_at"] is None
    assert cfg["publishing"]["deployment"]["auto_deploy"] is False
    assert "nothing was pushed" in deploy_if_enabled(cfg, "site", [saved["slug"]])
    with pytest.raises(NotImplementedError):
        VercelAdapter().deploy("site", [])


def test_fake_freshness_prevention(cfg, make):
    meta, body, p = good_article(cfg, make)
    path, _ = A.save_article(meta, body, p, cfg)
    first, first_body = A.parse(path.read_text())
    # Saving again without changing the text must not move updated_at
    path, _ = A.save_article(dict(first), first_body, p, cfg)
    again, _ = A.parse(path.read_text())
    assert again["updated_at"] == first["updated_at"] and again["published_at"] is None
    now = A.now_utc()
    published = dict(first, status="PUBLISHED", published_at=A.iso(now - timedelta(days=3)), updated_at=A.iso(now - timedelta(days=3)))
    assert A.check_dates(published) == []
    bumped = dict(published, updated_at=A.iso(now))
    assert any("did not change" in i["detail"] for i in A.check_dates(bumped, published, first_body, first_body))
    redated = dict(published, published_at=A.iso(now))
    assert any("published_at was changed" in i["detail"] for i in A.check_dates(redated, published))
    assert A.check_dates(dict(published, published_at=A.iso(now + timedelta(days=1))))     # future date
    assert A.check_dates(dict(first, status="DRAFT", published_at=A.iso(now)))             # dated but unpublished
    # A genuine edit does move updated_at, and never touches published_at
    path.write_text(A.dump(published, first_body))
    path, _ = A.save_article(dict(published), first_body.replace("mostly affects", "chiefly affects"), p, cfg)
    edited, _ = A.parse(path.read_text())
    assert edited["published_at"] == published["published_at"] and edited["updated_at"] > published["updated_at"]
    assert edited["status"] == "REVIEW_REQUIRED"       # an edited article needs approving again


def test_article_metadata_validation(cfg, make):
    meta, body, p = good_article(cfg, make)
    path, report = A.save_article(meta, body, p, cfg)
    saved, _ = A.parse(path.read_text())
    assert not [i for i in A.validate_metadata(saved, cfg) if i["level"] == "error"]
    for key in ("story_id", "angle_id", "title", "slug", "description", "published_at", "updated_at",
                "editorial_bucket", "verification_status", "author", "tags", "sources", "status"):
        assert key in saved
    broken = dict(saved, slug="Not A Slug", status="LIVE", editorial_bucket="HOT", description="short", sources=[{"name": "x"}])
    details = " | ".join(i["detail"] for i in A.validate_metadata(broken, cfg))
    for expected in ("slug", "status", "editorial_bucket", "description", "source"):
        assert expected in details
    # Invented bylines are flagged
    assert any(i["code"] == "byline" for i in A.validate_metadata(dict(saved, author="Jane Reporter, Senior Editor"), cfg))
    assert A.check_links(dict(saved, related_content=["no-such-article"]), body, cfg)


def _node_ok() -> bool:
    """Astro needs Node 22.12 or newer; an older Node on PATH is a toolchain gap, not a site bug."""
    if not shutil.which("node"):
        return False
    v = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")
    return (int(v[0]), int(v[1])) >= (22, 12) if len(v) >= 2 and v[0].isdigit() else False


def test_site_build():
    site = ROOT / "site"
    if not shutil.which("npm") or not (site / "node_modules").exists():
        pytest.skip("site toolchain not installed: run `npm install` in site/")
    if not _node_ok():
        pytest.skip("the site needs Node 22.12 or newer on PATH (for example `nvm use 22`)")
    r = subprocess.run(["npm", "run", "build"], cwd=site, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    dist = site / "dist"
    dist = dist / "client" if (dist / "client").exists() else dist     # the Cloudflare adapter builds pages into dist/client
    for page in ("index.html", "latest/index.html", "news/index.html", "discoveries/index.html",
                 "explainers/index.html", "guides/index.html", "about/index.html",
                 "editorial-standards/index.html", "ai-disclosure/index.html", "rss.xml", "sitemap.xml", "robots.txt"):
        assert (dist / page).exists(), page
    home = (dist / "index.html").read_text()
    assert 'rel="canonical"' in home and 'property="og:title"' in home and 'name="twitter:card"' in home
    # Only PUBLISHED articles are built or listed: drafts and reviews never reach a production build
    published = {m["slug"] for m, _, _ in A.all_articles({"publishing": {}, "root": ROOT}) if m.get("status") == "PUBLISHED"}
    built = {p.parent.name for p in (dist / "articles").glob("*/index.html")} if (dist / "articles").exists() else set()
    assert built == published
    sitemap = (dist / "sitemap.xml").read_text()
    assert all(f"/articles/{slug}/" in sitemap for slug in published) and sitemap.count("/articles/") == len(published)


def test_site_is_the_simple_version_with_nothing_commercial_on_it():
    """The site was reverted to its first version on 7 Oct 2026: articles, listings and three standing
    pages. The expanded version (ads, affiliate, newsletter, games, videos) is kept in site-archive/."""
    site = ROOT / "site"
    pages = {p.name for p in (site / "src" / "pages").iterdir()}
    assert pages == {"index.astro", "latest.astro", "news.astro", "tech.astro", "discoveries.astro", "explainers.astro", "guides.astro",
                     "about.astro", "editorial-standards.astro", "ai-disclosure.astro", "privacy.astro", "404.astro", "articles",
                     "rss.xml.ts", "sitemap.xml.ts", "robots.txt.ts"}
    assert {p.name for p in (site / "src" / "components").iterdir()} == {"ArticleCard.astro", "Badge.astro", "Cover.astro", "Listing.astro"}
    assert len(list((site / "src" / "content" / "articles").glob("*.md"))) >= 3
    assert (ROOT / "site-archive" / "expanded-2026-10-05" / "src" / "pages" / "newsletter.astro").exists()
    dist = site / "dist"
    dist = dist / "client" if (dist / "client").exists() else dist     # the Cloudflare adapter builds pages into dist/client
    if (dist / "index.html").exists():
        home = (dist / "index.html").read_text()
        for label in ("Latest", "News", "Discoveries", "Explainers", "Guides", "About"):
            assert f">{label}</a>" in home, label
        assert "ad-slot" not in home and "data-newsletter" not in home and 'rel="sponsored' not in home and "ld.js" not in home
