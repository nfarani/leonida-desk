"""CLUSTER: attach new items to existing underlying stories, merge duplicate stories, or create new ones.

Pass 1 attaches each new item to the story it fingerprints to (fingerprint.py).
Pass 2 merges stories that turn out to be the same event (including duplicates already in the db).
Pass 3 sends borderline pairs to Claude (llm.py) when available; otherwise they are only reported.

Linking is deliberately not single-link: one roundup article that resembles two different stories
must not weld them together, so a merge needs a share of the items on both sides to agree.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .community import content_type
from .fingerprint import Fingerprinter
from .models import Item, Story

_STATUS_RANK = {"used": 3, "recommended": 2, "new": 1}


def is_material(item: Item, story: Story) -> bool:
    """A new item is a meaningful development only if it raises the story's evidence level:
    its first official source, or its first tier-1 source. A rewrite of what we already have is not."""
    others = [i for i in story.items if i is not item]
    if item.source_type == "primary":
        return not any(i.source_type == "primary" for i in others)
    if item.tier <= 1:
        return not any(i.source_type == "primary" or i.tier <= 1 for i in others)
    return False


def attach(story: Story, item: Item, now: datetime) -> None:
    story.items.append(item)
    story.new_items.append(item)
    story.last_updated_at = now
    if story.id is not None and is_material(item, story):
        story.last_material_update_at = now


def _label(s: Story) -> str:
    return f"#{s.id} {s.headline[:70]}" if s.id else s.headline[:70]


def merge_into(target: Story, src: Story, now: datetime) -> None:
    """Fold src into target. Keeps every source and the earliest timestamps; never refreshes freshness."""
    target.items.extend(src.items)
    target.new_items.extend(src.new_items)
    firsts = [t for t in (target.first_seen_at, src.first_seen_at) if t]
    target.first_seen_at = min(firsts) if firsts else now
    materials = [t for t in (target.last_material_update_at, src.last_material_update_at) if t]
    target.last_material_update_at = max(materials) if materials else None
    target.last_updated_at = now
    target.absorbed.extend([src, *src.absorbed])
    src.absorbed = []


def _survivor(a: Story, b: Story) -> tuple[Story, Story]:
    """(keep, fold). Prefer the story the editor already acted on, then one already in the db, then the oldest."""
    def key(s: Story):
        return (_STATUS_RANK.get(s.status, 0), s.id is not None, -(s.id or 0), -s.event_time.timestamp())
    return (a, b) if key(a) >= key(b) else (b, a)


def refresh_headline(s: Story) -> None:
    """After a merge the headline should come from the most authoritative source, not a Reddit title."""
    if not s.headline or s.headline in {i.title for i in s.items}:
        s.headline = s.best_item().title


def cluster(new_items: list[Item], existing: list[Story], cfg: dict, adjudicate=None) -> tuple[list[Story], dict]:
    c = cfg["settings"]["clustering"]
    ratio = c.get("merge_link_ratio", 0.25)
    standalone = set(cfg["settings"]["community"]["standalone_types"])
    now = datetime.now(timezone.utc)
    stories = list(existing)
    fp = Fingerprinter(cfg, new_items + [i for s in existing for i in s.items])

    def substantive(i: Item) -> bool:
        """Chatter and unclassified community posts can join a story but never bridge two."""
        return i.source_type != "community" or content_type(i, cfg) in standalone

    def needed(n: int) -> int:
        return max(1, min(3, math.ceil(ratio * n)))

    created = attached = 0
    # Pass 1: oldest-first so the earliest report seeds the story
    for item in sorted(new_items, key=lambda i: i.when):
        best, best_key = None, (0, 0.0)
        for s in stories:
            rel, same, n = fp.relate_story(item, s)
            if rel.verdict == "same" and same >= needed(n) and (same / n, rel.score) > best_key:
                best, best_key = s, (same / n, rel.score)
        if best is not None:
            attach(best, item, now)
            attached += 1
            continue
        stories.append(Story(items=[item], new_items=[item], headline=item.title, first_seen_at=now,
                             last_updated_at=now))
        created += 1

    def link(a: Story, b: Story):
        """(share of item pairs that are the same event, best relation) between two stories."""
        a_items = [i for i in a.items if substantive(i)]
        b_n = sum(1 for i in b.items if substantive(i))
        if not a_items or not b_n:
            return 0.0, None
        total, best = 0, None
        for it in a_items:
            rel, same, _ = fp.relate_story(it, b, only=substantive)
            total += same
            if best is None or rel.score > best.score:
                best = rel
        ok = total >= needed(len(a_items)) and total >= needed(b_n) and total / (len(a_items) * b_n) >= ratio / 2
        return (total / (len(a_items) * b_n) if ok else 0.0), best

    # Pass 2: merge stories that are the same event, strongest link first. A story the editor
    # rejected is never merged into anything.
    merges: list[dict] = []
    live = [s for s in stories if s.status != "rejected"]
    cands: dict[tuple[int, int], tuple] = {}
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            share, rel = link(a, b)
            if share:
                cands[(id(a), id(b))] = (share, a, b, rel)
    while cands:
        key = max(cands, key=lambda k: cands[k][0])
        _, a, b, rel = cands.pop(key)
        keep, fold = _survivor(a, b)
        merges.append({"into": _label(keep), "absorbed": _label(fold), "why": rel.reason})
        merge_into(keep, fold, now)
        stories.remove(fold)
        live.remove(fold)
        # Only links that touch the merged story can have changed
        cands = {k: v for k, v in cands.items() if id(fold) not in k and id(keep) not in k}
        for other in live:
            if other is not keep:
                share, rel = link(keep, other)
                if share:
                    cands[(id(keep), id(other))] = (share, keep, other, rel)

    # Pass 3: borderline pairs -> Claude if available, otherwise report them as probable duplicates
    borderline: list[tuple[Story, Story, float, str]] = []
    live = [s for s in stories if s.status != "rejected"]
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            rels = [fp.relate_story(it, b, only=substantive)[0] for it in a.items if substantive(it)]
            rels = [r for r in rels if r.verdict in ("borderline", "same")]
            if rels:
                r = max(rels, key=lambda r: r.score)
                borderline.append((a, b, r.score, r.reason))
    borderline.sort(key=lambda x: x[2], reverse=True)

    llm_merged, unresolved = 0, borderline
    if adjudicate and borderline and c.get("llm_adjudication"):
        asked, unresolved = borderline[:30], borderline[30:]
        decisions = adjudicate([(a.best_item(), b, sim) for a, b, sim, _ in asked])
        for (a, b, sim, why), same in zip(asked, decisions):
            if a not in stories or b not in stories:
                continue
            if not same:
                continue
            keep, fold = _survivor(a, b)
            merges.append({"into": _label(keep), "absorbed": _label(fold), "why": f"Claude: {why}"})
            merge_into(keep, fold, now)
            stories.remove(fold)
            llm_merged += 1

    for s in stories:
        if s.new_items or s.absorbed:
            refresh_headline(s)

    return stories, {
        "attached": attached, "created": created, "merged": len(merges), "llm_merged": llm_merged,
        "borderline": len(borderline), "merges": merges,
        "probable_duplicates": [{"a": _label(a), "b": _label(b), "why": why}
                                for a, b, _, why in unresolved if a in stories and b in stories][:40],
    }
