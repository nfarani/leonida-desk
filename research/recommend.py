"""RECOMMEND: the daily hot list, POST NOW flags, and every editorial field filled honestly."""
from __future__ import annotations

from . import desk
from .llm import enforce_hook_hedging
from .models import Story

RISK_BY_LABEL = {
    "CONFIRMED": "Low: official source. Still link the primary source and avoid embellishing.",
    "HIGH_CONFIDENCE_REPORT": "Not officially confirmed by Rockstar/Take-Two. Attribute to the outlet ('X reports...').",
    "CREDIBLE_RUMOUR": "Unconfirmed rumour. Must be framed as a rumour wherever it is used.",
    "COMMUNITY_DISCOVERY": "Community find in official material; the interpretation is unverified. Show the evidence, label the interpretation.",
    "THEORY": "Fan theory. Must be explicitly framed as theory, not fact.",
    "SPECULATION": "Weakly sourced. Only usable as 'is this real?' content with a clear caveat.",
    "FALSE_OR_DEBUNKED": "False claim. Only usable as a debunk; never repeat the claim without the correction.",
}
HEDGE_PREFIX = {
    "HIGH_CONFIDENCE_REPORT": "According to a new report, ",
    "CREDIBLE_RUMOUR": "A new rumour claims ",
    "COMMUNITY_DISCOVERY": "Fans have spotted something: ",
    "THEORY": "There's a fan theory that ",
    "SPECULATION": "Is this real? People are claiming ",
    "FALSE_OR_DEBUNKED": "No, this isn't real: ",
}


def fallback_editorial(s: Story, cfg: dict) -> None:
    best = s.best_item()
    e = s.editorial
    e.setdefault("format", "News brief")
    if not e.get("why_care"):
        e["why_care"] = (f"{len(s.publishers())} outlet(s)/communities are discussing it"
                         + (" and it is gaining Reddit traction" if s.dims.get("existing_demand", 0) > .5 else "")
                         + f"; fits the '{s.content_cluster.replace('_', ' ')}' interest cluster.")
    e.setdefault("angle", "Editor to define: heuristic mode (no Claude judgement this run).")
    if not e.get("hook"):
        e["hook"] = HEDGE_PREFIX.get(s.verification_status, "") + s.headline.rstrip(".")
    if not s.summary:
        s.summary = best.snippet[:280] or best.title
    if not s.reasoning:
        s.reasoning = "Heuristic scoring (no Claude judgement this run)."


def _finish(s: Story, cfg: dict) -> None:
    fallback_editorial(s, cfg)
    e = s.editorial
    base_risk = RISK_BY_LABEL[s.verification_status]
    if base_risk not in (e.get("risk") or ""):
        e["risk"] = base_risk if not e.get("risk") else f"{e['risk']} ({base_risk})"
    if s.verification_status == "FALSE_OR_DEBUNKED":
        s.content_cluster = "debunking"
    enforce_hook_hedging(s)


def recommend(ranked: list[Story], cfg: dict, now=None, all_stories: list[Story] | None = None,
              covered_topics: set[str] = frozenset()) -> tuple[list[tuple[Story, bool]], dict]:
    """Returns (the hot list in rank order with its POST NOW flags, desk view). Stories that are not
    hot or not sourced well enough are listed as skipped instead of padding the list."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    pn = cfg["settings"]["ranking"]["post_now"]
    for s in ranked:
        desk.assess(s, cfg, now)
    view = desk.hot_list(ranked, cfg, now)
    post_now: set[int] = set()
    for s in view["hot"]:
        if (len(post_now) < pn["count"] and s.opportunity >= pn["min_opportunity"]
                and s.freshness >= pn["min_freshness"] and s.saturation <= pn["max_saturation"]
                and s.verification_status not in pn["excluded_labels"]):
            post_now.add(id(s))
    out = []
    for s in view["hot"] + view["radar"]:
        _finish(s, cfg)
        s.status = "recommended" if s.status == "new" else s.status
    for s in view["hot"]:
        out.append((s, id(s) in post_now))
    for s in ranked:
        if not s.editorial.get("hook"):
            fallback_editorial(s, cfg)
    return out, view
