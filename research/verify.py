"""VERIFY: assign exactly one verification label per story.

Evidence ceilings are enforced in code. Claude may lower a label or pick within the ceiling,
but can never exceed what the attached sources support.
"""
from __future__ import annotations

from .community import community_types, is_community_only
from .models import CONFIDENCE_ORDER, Story


def evidence(story: Story, cfg: dict | None = None) -> dict:
    j = [i for i in story.items if i.source_type == "journalism"]
    types = community_types(story, cfg) if cfg else []
    return {
        # A community post only supports COMMUNITY_DISCOVERY if it points at something observable.
        "observable": "OBSERVABLE_DISCOVERY" in types,
        "community_theory": "THEORY" in types,
        "has_primary": any(i.source_type == "primary" for i in story.items),
        "tier1": len({i.publisher for i in j if i.tier <= 1}),
        "tier2": len({i.publisher for i in j if i.tier == 2}),
        "journalism": len({i.publisher for i in j}),
        "community": sum(1 for i in story.items if i.source_type == "community"),
        "text": " ".join(f"{i.title} {i.snippet}" for i in story.items).lower(),
    }


def ceiling(ev: dict) -> str:
    if ev["has_primary"]:
        return "CONFIRMED"
    if ev["tier1"]:
        return "HIGH_CONFIDENCE_REPORT"
    if ev["journalism"]:
        return "CREDIBLE_RUMOUR"
    # Community-only: discussion, questions, memes and wishlists are never a discovery.
    return "COMMUNITY_DISCOVERY" if ev.get("observable") else "THEORY"


def clip(label: str, ev: dict, fallback: str) -> str:
    """Never exceed the evidence ceiling. FALSE_OR_DEBUNKED needs authoritative support."""
    if label == "FALSE_OR_DEBUNKED":
        return label if (ev["has_primary"] or ev["tier1"]) else fallback
    if label not in CONFIDENCE_ORDER:
        return fallback
    cap = ceiling(ev)
    return label if CONFIDENCE_ORDER.index(label) >= CONFIDENCE_ORDER.index(cap) else cap


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def heuristic_label(story: Story, cfg: dict) -> str:
    kw = cfg["verification"]["keywords"]
    ev = evidence(story, cfg)
    t = ev["text"]
    if _has(t, kw["debunk"]) and (ev["has_primary"] or ev["tier1"]):
        label = "FALSE_OR_DEBUNKED"
    elif ev["has_primary"]:
        label = "CONFIRMED"
    elif ev["journalism"]:
        if _has(t, kw["rumour"]):
            label = "CREDIBLE_RUMOUR" if (ev["tier1"] or ev["tier2"] >= 2) else "SPECULATION"
        elif _has(t, kw["theory"]):
            label = "THEORY"
        elif ev["tier1"] and (_has(t, kw["official"]) or _has(t, kw["report"]) or ev["tier1"] >= 2):
            label = "HIGH_CONFIDENCE_REPORT"
        elif ev["tier1"] or ev["tier2"]:
            label = "CREDIBLE_RUMOUR"
        else:
            label = "SPECULATION"
    else:
        # Community-only: the label follows the deterministic content type (community.py),
        # not loose keywords. A rumour with no journalism behind it is speculation.
        if ev["observable"]:
            label = "COMMUNITY_DISCOVERY"
        elif ev["community_theory"]:
            label = "THEORY"
        else:
            label = "SPECULATION"
    return clip(label, ev, "SPECULATION")


def verify(stories: list[Story], cfg: dict) -> dict:
    """Label every story that changed this run. Community-only stories are re-checked every run so a
    classifier fix reaches stories already in the db; a re-check can lower a label but never raise it.
    Returns the label transitions for the run diagnostics."""
    transitions: dict[str, int] = {}
    community = 0
    for s in stories:
        changed = bool(s.new_items or s.absorbed or s.id is None)
        if not (changed or is_community_only(s)):
            continue
        label = heuristic_label(s, cfg)
        prev = s.previous_status
        if not changed and prev in CONFIDENCE_ORDER and label in CONFIDENCE_ORDER:
            label = max(prev, label, key=CONFIDENCE_ORDER.index)
        s.verification_status = label
        if prev and prev != label and s.id is not None:
            transitions[f"{prev} -> {label}"] = transitions.get(f"{prev} -> {label}", 0) + 1
            community += is_community_only(s)
            # A label change caused by new evidence is a meaningful development.
            # One caused by a merge or by reclassification is bookkeeping and must not refresh freshness.
            if s.new_items and not s.absorbed:
                s.last_material_update_at = s.last_updated_at
    return {"transitions": transitions, "community_stories_relabelled": community}
