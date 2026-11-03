"""ARTICLES: evidence packets, article files, fact checks, scoring and the publication gate.

Evidence first: an article is written from an evidence packet, and every factual paragraph cites a
claim in that packet. The checks here are deterministic so the same draft always gets the same
verdict. Nothing in this module deploys anything.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import resolve
from .desk import BUCKETS, label_at_least
from .models import CONFIDENCE_ORDER, LABELS, Story
from .text import similarity, tokens

STATUSES = ["DRAFT", "REVIEW_REQUIRED", "APPROVED", "PUBLISHED", "REJECTED"]
GATES = ["AUTO_PUBLISH_ELIGIBLE", "REVIEW_REQUIRED", "DO_NOT_PUBLISH"]
REQUIRED = ["article_id", "story_id", "title", "slug", "description", "author", "updated_at",
            "editorial_bucket", "verification_status", "tags", "sources", "status"]
CITE = re.compile(r"\[\^(c\d+)\]")
CITATIONS_START, CITATIONS_END = "<!-- citations:start -->", "<!-- citations:end -->"
_QUOTE = re.compile(r"[\"“]([^\"”]{12,})[\"”]")
_ATTRIBUTION = re.compile(r"\b(said|says|told|confirmed|confirms|announced|announces|revealed|reveals|stated|"
                          r"according to|reported|reports)\b", re.I)
_UPGRADE = re.compile(r"(?<!not )(?<!un)\b(confirmed|confirms|official(ly)?)\b", re.I)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def articles_dir(cfg: dict) -> Path:
    return resolve(cfg, cfg["publishing"].get("articles_dir", "site/src/content/articles"))


def evidence_dir(cfg: dict) -> Path:
    return resolve(cfg, cfg["publishing"].get("evidence_dir", "data/evidence"))


def slugify(title: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-")[:80].strip("-")


# ---------------------------------------------------------------- evidence packet
def source_level(source_type: str, tier: int) -> str:
    """The strongest label one source can support on its own (mirrors the ceilings in verify.py)."""
    if source_type == "primary":
        return "CONFIRMED"
    if source_type == "journalism":
        return "HIGH_CONFIDENCE_REPORT" if tier <= 1 else "CREDIBLE_RUMOUR"
    return "THEORY"


def weaker(a: str, b: str) -> str:
    # A debunk story's sources are still graded by what they are; the label itself is not a confidence level
    if "FALSE_OR_DEBUNKED" in (a, b):
        return a if b == "FALSE_OR_DEBUNKED" else b
    return max(a, b, key=CONFIDENCE_ORDER.index)


def build_packet(stories: list[Story], cfg: dict, angle: str = "", angle_id: str | None = None,
                 bucket: str | None = None) -> dict:
    """Start an evidence packet from stored sources. Seed claims are headline-level only: the writer
    must open each source, then add real claims (with paraphrased evidence) before drafting."""
    lead = stories[0]
    # The article is about the lead story's event, so it takes that story's label. Supporting stories
    # add sources; they cannot raise the label, and each claim still carries its own source's level.
    label = lead.verification_status
    sources, claims, seen = [], [], set()
    for s in stories:
        for it in sorted(s.items, key=lambda i: (i.tier, i.when)):
            if it.url in seen or it.source_type == "community" and it.content_type in ("MEME", "QUESTION",
                                                                                      "DISCUSSION", "WISHLIST"):
                continue
            seen.add(it.url)
            sid = f"s{len(sources) + 1}"
            sources.append({"id": sid, "story_id": s.id, "publisher": it.publisher, "url": it.url,
                            "title": it.title, "published_at": iso(it.published_at), "tier": it.tier,
                            "source_type": it.source_type, "opened": False, "opened_at": None, "note": ""})
            claims.append({"id": f"c{len(claims) + 1}", "kind": "headline",
                           "claim": f"{it.publisher} published a piece headlined: {it.title}",
                           "source_id": sid, "source_url": it.url, "source_date": iso(it.published_at),
                           "verification": weaker(source_level(it.source_type, it.tier), s.verification_status),
                           "evidence": (it.snippet or it.title)[:400], "quote": None})
    return {"packet_id": f"story-{lead.id}" + (f"-{slugify(angle_id)}" if angle_id else ""),
            "story_id": lead.id, "parent_event_id": lead.id if len(stories) > 1 else None,
            "story_ids": [s.id for s in stories], "angle_id": angle_id, "angle": angle,
            "editorial_bucket": bucket or (lead.desk or {}).get("bucket"), "story_label": label,
            "built_at": iso(now_utc()), "sources": sources, "claims": claims, "conflicts": [],
            "media": {"status": "none", "note": "No hero media selected."}, "sensitive": False}


def add_claim(packet: dict, claim: str, source_id: str, evidence: str, quote: str | None = None,
              verification: str | None = None) -> dict:
    """Add a claim that the writer verified by opening the source. The claim inherits the source's
    ceiling; a writer may lower it but never raise it."""
    src = next(s for s in packet["sources"] if s["id"] == source_id)
    ceiling = weaker(source_level(src["source_type"], src["tier"]), "CONFIRMED")
    level = weaker(verification, ceiling) if verification else ceiling
    c = {"id": f"c{len(packet['claims']) + 1}", "kind": "fact", "claim": claim, "source_id": source_id,
         "source_url": src["url"], "source_date": src["published_at"], "verification": level,
         "evidence": evidence, "quote": quote}
    packet["claims"].append(c)
    return c


def save_packet(packet: dict, cfg: dict) -> Path:
    d = evidence_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{packet['packet_id']}.json"
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
    return path


def load_packet(ref: str | Path, cfg: dict) -> dict:
    p = Path(ref)
    if not p.is_absolute():
        p = evidence_dir(cfg) / (p.name if p.suffix == ".json" else f"{ref}.json")
    return json.loads(p.read_text())


# ---------------------------------------------------------------- article files
def parse(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("article has no front matter")
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.lstrip("\n")


def dump(meta: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n" + body.rstrip() + "\n"


def load_article(slug: str, cfg: dict) -> tuple[dict, str, Path]:
    path = articles_dir(cfg) / f"{slug}.md"
    meta, body = parse(path.read_text())
    return meta, body, path


def all_articles(cfg: dict) -> list[tuple[dict, str, Path]]:
    d = articles_dir(cfg)
    out = []
    for p in sorted(d.glob("*.md")) if d.exists() else []:
        try:
            meta, body = parse(p.read_text())
        except (ValueError, yaml.YAMLError):
            continue
        out.append((meta, body, p))
    return out


def covered_topics(cfg: dict) -> set[str]:
    """Evergreen topics that already have a live article, so /morning stops proposing them."""
    return {str(m.get("angle_id", ""))[len("evergreen:"):] for m, _, _ in all_articles(cfg)
            if str(m.get("angle_id", "")).startswith("evergreen:") and m.get("status") != "REJECTED"}


def prose(body: str) -> str:
    """Body without the generated citations block."""
    if CITATIONS_START in body:
        body = body.split(CITATIONS_START)[0]
    return body.strip()


def content_hash(body: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", prose(body)).encode()).hexdigest()[:16]


def citations_block(body: str, packet: dict) -> str:
    """Footnote definitions for every claim cited in the body, generated from the packet."""
    claims = {c["id"]: c for c in packet["claims"]}
    sources = {s["id"]: s for s in packet["sources"]}
    lines = [CITATIONS_START]
    for cid in dict.fromkeys(CITE.findall(prose(body))):
        c = claims.get(cid)
        if not c:
            continue
        s = sources.get(c["source_id"], {})
        date = (c.get("source_date") or "")[:10] or "date not shown"
        lines.append(f"[^{cid}]: [{s.get('publisher', 'Source')}: {s.get('title', '').strip()}]({c['source_url']}), {date}.")
    lines.append(CITATIONS_END)
    return "\n".join(lines)


def with_citations(body: str, packet: dict) -> str:
    return prose(body) + "\n\n" + citations_block(body, packet) + "\n"


# ---------------------------------------------------------------- checks
def _paragraphs(body: str, cfg: dict) -> list[tuple[str, bool]]:
    """(paragraph, is_analysis) for every prose paragraph. A paragraph is analysis when it sits under
    a heading listed in publishing.yaml -> article.analysis_headings."""
    marks = [h.lower() for h in cfg["publishing"]["article"]["analysis_headings"]]
    out, analysis = [], False
    for block in re.split(r"\n\s*\n", prose(body)):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            head = block.lstrip("#").strip().lower()
            analysis = any(head.startswith(m) or m in head for m in marks)
            continue
        out.append((block, analysis))
    return out


def fact_check(meta: dict, body: str, packet: dict, cfg: dict) -> list[dict]:
    """Every problem found, as {level: error|warning, code, detail}. Errors block approval."""
    issues: list[dict] = []

    def add(level: str, code: str, detail: str) -> None:
        issues.append({"level": level, "code": code, "detail": detail})

    claims = {c["id"]: c for c in packet["claims"]}
    source_urls = {s["url"] for s in packet["sources"]}
    for cid in sorted(set(CITE.findall(prose(body)))):
        if cid not in claims:
            add("error", "unknown_citation", f"[^{cid}] is not in the evidence packet")
        elif claims[cid]["source_url"] not in source_urls:
            add("error", "unsourced_claim", f"claim {cid} points at a URL that is not a stored source")
    quotes = [c["quote"] for c in packet["claims"] if c.get("quote")]
    norm = lambda t: re.sub(r"\s+", " ", t.replace("’", "'").replace("‘", "'")).strip().lower()
    for block, analysis in _paragraphs(body, cfg):
        text = CITE.sub("", block)
        cited = bool(CITE.search(block))
        short = re.sub(r"\s+", " ", text)[:90]
        for q in _QUOTE.findall(text):
            if len(q.split()) >= 4 and not any(norm(q) in norm(k) for k in quotes):
                add("error", "unsupported_quote", f"quote not found verbatim in the evidence packet: \"{q[:80]}\"")
        if cited:
            continue
        bare = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)       # a cross-reference link is navigation, not a claim
        if not analysis and len(bare.split()) >= 8 and not text.lstrip().startswith((">", "|", "<", "*This", "_This")):
            add("error", "unsupported_claim", f"paragraph states facts with no citation: \"{short}\"")
        elif analysis and (re.search(r"\d", text) or _ATTRIBUTION.search(text)):
            add("error", "unsupported_claim", f"analysis introduces a number or attribution with no citation: \"{short}\"")
    label, story_label = meta.get("verification_status"), packet.get("story_label")
    if label in CONFIDENCE_ORDER and story_label in CONFIDENCE_ORDER and not label_at_least(story_label, label):
        add("error", "label_upgraded", f"article says {label} but the evidence supports {story_label} at most")
    if label != "CONFIRMED":
        for field in ("title", "description"):
            if _UPGRADE.search(str(meta.get(field, ""))):
                add("error", "rumour_upgraded", f"{field} uses confirmed/official wording for a {label} story")
    for c in packet.get("conflicts", []):
        if not c.get("resolved"):
            add("warning", "unresolved_conflict", c.get("description", "sources disagree"))
    cited_ids = set(CITE.findall(prose(body)))
    unopened = sorted({claims[c]["source_id"] for c in cited_ids if c in claims} -
                      {s["id"] for s in packet["sources"] if s.get("opened")})
    if unopened:
        add("warning", "source_not_opened", f"cited sources not opened and rechecked: {', '.join(unopened)}")
    return issues


def validate_metadata(meta: dict, cfg: dict) -> list[dict]:
    a = cfg["publishing"]["article"]
    issues = []

    def add(detail: str) -> None:
        issues.append({"level": "error", "code": "metadata", "detail": detail})

    for k in REQUIRED:
        if meta.get(k) in (None, "", []) and k != "story_id":
            add(f"missing {k}")
    if meta.get("status") not in STATUSES:
        add(f"status must be one of {STATUSES}")
    if meta.get("editorial_bucket") not in BUCKETS:
        add(f"editorial_bucket must be one of {BUCKETS}")
    if meta.get("verification_status") not in LABELS:
        add("verification_status is not a valid label")
    if meta.get("slug") and meta["slug"] != slugify(meta["slug"]):
        add("slug must be lowercase words joined by hyphens")
    lo, hi = a["title_chars"]
    if not lo <= len(str(meta.get("title", ""))) <= hi:
        add(f"title must be {lo}-{hi} characters")
    lo, hi = a["description_chars"]
    if not lo <= len(str(meta.get("description", ""))) <= hi:
        add(f"description must be {lo}-{hi} characters")
    for s in meta.get("sources") or []:
        if not (isinstance(s, dict) and str(s.get("url", "")).startswith("http") and s.get("name")):
            add("every source needs a name and an http(s) url")
            break
    if meta.get("author") and meta["author"] != cfg["publishing"]["publication"]["byline"]:
        issues.append({"level": "warning", "code": "byline",
                       "detail": "author is not the publication byline; never invent a named journalist"})
    issues += check_dates(meta)
    return issues


def _dt(v) -> datetime | None:
    if not v:
        return None
    d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def check_dates(meta: dict, previous: dict | None = None, body: str | None = None,
                previous_body: str | None = None) -> list[dict]:
    """Fake-freshness prevention. published_at is set once and never moves; updated_at may only
    advance when the text actually changed."""
    issues = []

    def add(detail: str) -> None:
        issues.append({"level": "error", "code": "fake_freshness", "detail": detail})

    pub, upd, now = _dt(meta.get("published_at")), _dt(meta.get("updated_at")), now_utc()
    if pub and pub > now:
        add("published_at is in the future")
    if upd and upd > now:
        add("updated_at is in the future")
    if pub and upd and upd < pub:
        add("updated_at is earlier than published_at")
    if meta.get("status") != "PUBLISHED" and pub:
        add("published_at is set on an article that has not been published")
    if previous:
        old_pub = _dt(previous.get("published_at"))
        if old_pub and pub != old_pub:
            add("published_at was changed after first publication")
        if (body is not None and previous_body is not None and content_hash(body) == content_hash(previous_body)
                and _dt(previous.get("updated_at")) and upd and upd > _dt(previous["updated_at"])):
            add("updated_at was advanced although the article text did not change")
    return issues


def find_duplicates(meta: dict, body: str, cfg: dict) -> list[str]:
    """Slugs of other live articles that cover the same story and angle, or read the same."""
    thr = cfg["publishing"]["article"]["duplicate_similarity"]
    mine_title, mine_body = tokens(str(meta.get("title", ""))), tokens(prose(body))
    out = []
    for other, obody, _ in all_articles(cfg):
        if other.get("slug") == meta.get("slug") or other.get("status") == "REJECTED":
            continue
        same_angle = (meta.get("story_id") is not None and other.get("story_id") == meta.get("story_id")
                      and other.get("angle_id") == meta.get("angle_id"))
        body_sim = len(mine_body & tokens(prose(obody))) / max(1, len(mine_body | tokens(prose(obody))))
        if same_angle or similarity(mine_title, tokens(str(other.get("title", "")))) >= thr or body_sim >= thr:
            out.append(other["slug"])
    return out


def check_links(meta: dict, body: str, cfg: dict) -> list[dict]:
    live = {m["slug"] for m, _, _ in all_articles(cfg) if m.get("status") != "REJECTED"}
    issues = []
    for slug in meta.get("related_content") or []:
        if slug not in live:
            issues.append({"level": "error", "code": "broken_link", "detail": f"related_content: no article '{slug}'"})
    for target in re.findall(r"\]\(/articles/([a-z0-9\-]+)/?\)", body):
        if target not in live:
            issues.append({"level": "error", "code": "broken_link", "detail": f"internal link to missing article '{target}'"})
    return issues


# ---------------------------------------------------------------- scores
def _shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def source_overlap(body: str, packet: dict) -> float:
    """Share of the article's 5-word runs that also appear in source text. Quotes are excluded."""
    text = _QUOTE.sub(" ", CITE.sub("", prose(body)))
    mine = _shingles(text)
    if not mine:
        return 0.0
    theirs: set = set()
    for s in packet["sources"]:
        theirs |= _shingles(s.get("title", ""))
    for c in packet["claims"]:
        if c.get("kind") == "headline":
            theirs |= _shingles(c.get("evidence", ""))
    return round(len(mine & theirs) / len(mine), 3)


def cited_claims(body: str, packet: dict) -> list[dict]:
    ids = set(CITE.findall(prose(body)))
    return [c for c in packet["claims"] if c["id"] in ids]


def originality_score(body: str, packet: dict, cfg: dict) -> int:
    """0-100. Rewards synthesis across sources and clearly separated analysis; punishes copying."""
    paras = _paragraphs(body, cfg)
    words = sum(len(p.split()) for p, _ in paras) or 1
    analysis_words = sum(len(p.split()) for p, a in paras if a)
    used = {c["source_id"] for c in cited_claims(body, packet)}
    synthesis = min(1.0, len(used) / 3)
    analysis = min(1.0, (analysis_words / words) / 0.3)
    structure = min(1.0, (bool(re.search(r"^\|.+\|", body, re.M)) + bool(re.search(r"^[-*] ", body, re.M))
                          + bool(re.search(r"^#+ .*(timeline|compar|context)", body, re.M | re.I))) / 2)
    overlap = source_overlap(body, packet)
    score = 100 * (1 - overlap) * (0.15 + 0.35 * synthesis + 0.35 * analysis + 0.15 * structure)
    if overlap >= cfg["publishing"]["article"]["rewrite_overlap"]:
        score = min(score, 30)
    return round(score)


def quality_score(meta: dict, body: str, packet: dict, issues: list[dict], cfg: dict) -> int:
    a = cfg["publishing"]["article"]
    paras = [(p, an) for p, an in _paragraphs(body, cfg) if len(p.split()) >= 8]
    factual = [p for p, an in paras if not an]
    cited = sum(1 for p in factual if CITE.search(p)) / len(factual) if factual else 0.0
    errors = [i for i in issues if i["level"] == "error"]
    meta_ok = not any(i["code"] in ("metadata", "fake_freshness") for i in errors)
    unsupported = any(i["code"].startswith("unsupported") or i["code"] in ("unknown_citation", "unsourced_claim")
                      for i in errors)
    facts = [c for c in cited_claims(body, packet) if c.get("kind") == "fact"]
    depth = min(1.0, len(facts) / a["min_claims"])
    headings = len(re.findall(r"^## ", prose(body), re.M))
    conflicts = any(i["code"] == "unresolved_conflict" for i in issues)
    return round(20 * meta_ok + 30 * cited + 20 * (not unsupported) + 15 * depth
                 + 10 * min(1.0, headings / 2) + 5 * (not conflicts))


# ---------------------------------------------------------------- publication gate
def gate(meta: dict, body: str, packet: dict, issues: list[dict], originality: int, quality: int,
         duplicates: list[str], cfg: dict) -> tuple[str, list[str]]:
    """Deterministic. Returns (AUTO_PUBLISH_ELIGIBLE | REVIEW_REQUIRED | DO_NOT_PUBLISH, reasons)."""
    g, a = cfg["publishing"]["gate"], cfg["publishing"]["article"]
    label = meta.get("verification_status")
    facts = [c for c in cited_claims(body, packet) if c.get("kind") == "fact"]
    blocks, reviews = [], []
    if label in g["blocked_labels"]:
        blocks.append(f"unsupported speculation ({label})")
    if any(i["code"].startswith("unsupported") or i["code"] in ("unknown_citation", "unsourced_claim",
                                                               "label_upgraded", "rumour_upgraded")
           for i in issues if i["level"] == "error"):
        blocks.append("unsupported or unverifiable claims in the draft")
    if len(facts) < a["min_claims"]:
        blocks.append(f"thin story: {len(facts)} evidenced claims, needs {a['min_claims']}")
    if source_overlap(body, packet) >= a["rewrite_overlap"] or originality <= g["do_not_publish"]["max_originality"]:
        blocks.append("reads as a rewrite of its sources: insufficient added value")
    if quality <= g["do_not_publish"]["max_quality"]:
        blocks.append("quality too low")
    if duplicates:
        blocks.append(f"duplicate of existing article(s): {', '.join(duplicates)}")
    if blocks:
        return "DO_NOT_PUBLISH", blocks

    ap = g["auto_publish"]
    used = {c["source_id"] for c in facts}
    srcs = [s for s in packet["sources"] if s["id"] in used]
    primary = sum(1 for s in srcs if s["source_type"] == "primary")
    credible = {s["publisher"] for s in srcs if s["source_type"] in ("journalism", "primary")
                and s["tier"] <= ap["credible_max_tier"]}
    if label in g["review_labels"] or not label_at_least(label, ap["min_label"]):
        reviews.append(f"{label.replace('_', ' ').lower()} always needs an editor")
    if any(i["code"] == "unresolved_conflict" for i in issues):
        reviews.append("sources disagree and the conflict is unresolved")
    if any(i["level"] == "error" for i in issues):
        reviews.append("draft has errors to fix: " + "; ".join(sorted({i["code"] for i in issues if i["level"] == "error"})))
    if any(i["code"] == "source_not_opened" for i in issues):
        reviews.append("some cited sources were not reopened and checked")
    if packet.get("media", {}).get("status") == "uncertain":
        reviews.append("media or copyright status is uncertain")
    if packet.get("sensitive") or meta.get("sensitive"):
        reviews.append("sensitive or controversial factual claims")
    if originality < ap["min_originality"]:
        reviews.append(f"originality {originality} is below {ap['min_originality']}")
    if quality < ap["min_quality"]:
        reviews.append(f"quality {quality} is below {ap['min_quality']}")
    if not (primary >= ap["or_primary_sources"] or len(credible) >= ap["min_independent_sources"]):
        reviews.append(f"needs {ap['min_independent_sources']} independent credible sources or a primary source "
                       f"(has {len(credible)} credible, {primary} primary)")
    if reviews:
        return "REVIEW_REQUIRED", reviews
    return "AUTO_PUBLISH_ELIGIBLE", ["meets every auto-publish threshold"]


def evaluate(meta: dict, body: str, packet: dict, cfg: dict) -> dict:
    """Run every check and score; returns a report. Does not write anything."""
    issues = validate_metadata(meta, cfg) + fact_check(meta, body, packet, cfg) + check_links(meta, body, cfg)
    dupes = find_duplicates(meta, body, cfg)
    originality = originality_score(body, packet, cfg)
    quality = quality_score(meta, body, packet, issues, cfg)
    decision, reasons = gate(meta, body, packet, issues, originality, quality, dupes, cfg)
    return {"issues": issues, "duplicates": dupes, "originality_score": originality, "quality_score": quality,
            "source_overlap": source_overlap(body, packet), "gate": decision, "gate_reasons": reasons}


def status_for(decision: str, cfg: dict) -> str:
    """/article never publishes. A blocked draft stays DRAFT; everything else waits for an editor.
    Even an auto-publish-eligible piece is REVIEW_REQUIRED while the master switch is off."""
    if decision == "DO_NOT_PUBLISH":
        return "DRAFT"
    if decision == "AUTO_PUBLISH_ELIGIBLE" and cfg["publishing"]["gate"]["auto_publish"]["enabled"]:
        return "APPROVED"
    return "REVIEW_REQUIRED"


def save_article(meta: dict, body: str, packet: dict, cfg: dict) -> tuple[Path, dict]:
    """Evaluate, stamp scores and status, regenerate citations, write the file."""
    d = articles_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{meta['slug']}.md"
    previous, previous_body = (parse(path.read_text()) if path.exists() else (None, None))
    body = with_citations(body, packet)
    meta = dict(meta)
    meta.setdefault("article_id", meta["slug"])
    meta.setdefault("author", cfg["publishing"]["publication"]["byline"])
    meta.setdefault("created_at", (previous or {}).get("created_at") or iso(now_utc()))
    meta["published_at"] = (previous or {}).get("published_at")
    changed = previous_body is None or content_hash(body) != content_hash(previous_body)
    meta["updated_at"] = iso(now_utc()) if changed else previous.get("updated_at")
    meta["content_hash"] = content_hash(body)
    cited = {c["source_id"] for c in cited_claims(body, packet)}
    meta["sources"] = [{"name": s["publisher"], "url": s["url"], "title": s["title"], "published_at": s["published_at"]}
                       for s in packet["sources"] if s["id"] in cited]
    meta["evidence_packet"] = packet["packet_id"]
    meta.setdefault("status", "DRAFT")
    report = evaluate(meta, body, packet, cfg)
    meta.update(originality_score=report["originality_score"], quality_score=report["quality_score"],
                gate=report["gate"], gate_reasons=report["gate_reasons"])
    if meta["status"] in ("DRAFT", "REVIEW_REQUIRED"):
        meta["status"] = status_for(report["gate"], cfg)
    elif changed and meta["status"] in ("APPROVED", "PUBLISHED"):
        meta["status"] = "REVIEW_REQUIRED"      # an edited article needs approving again
    path.write_text(dump(meta, body))
    return path, report
