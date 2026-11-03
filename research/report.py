"""Render the daily hot list (Markdown for the editor, JSON for downstream stages)."""
from __future__ import annotations

import json
from datetime import datetime

from .models import Story
from .rank import CHATTER_REASON, TECH_REASON

BADGE = {"CONFIRMED": "🟢 CONFIRMED", "HIGH_CONFIDENCE_REPORT": "🔵 HIGH-CONFIDENCE REPORT",
         "CREDIBLE_RUMOUR": "🟡 CREDIBLE RUMOUR", "COMMUNITY_DISCOVERY": "🟣 COMMUNITY DISCOVERY",
         "THEORY": "🟠 THEORY", "SPECULATION": "⚪ SPECULATION", "FALSE_OR_DEBUNKED": "🔴 FALSE / DEBUNKED"}


def _ago(dt: datetime | None, now: datetime) -> str:
    if not dt:
        return "unknown"
    h = max(0.0, (now - dt).total_seconds() / 3600)
    rel = "just now" if h < 1 / 60 else f"{h * 60:.0f}m ago" if h < 1 else f"{h:.0f}h ago" if h < 48 else f"{h / 24:.0f}d ago"
    return f"{dt:%a %d %b %H:%M} UTC ({rel})"


def _sat(v: float) -> str:
    return f"{v:.0f}/100 ({'low' if v < 35 else 'medium' if v < 65 else 'high'})"


TYPE_TEXT = {"BREAKING": "Breaking", "DISCOVERY": "Discovery", "EXPLAINER": "Developing", "EVERGREEN": "Background"}
NO_HOT = "NO HOT STORIES RIGHT NOW."


def _label(s: Story) -> str:
    return BADGE[s.verification_status].split(" ", 1)[1].title()


def _pct(s: Story, dim: str) -> float:
    return 100 * s.dims.get(dim, 0)


def story_block(rank: int, s: Story, post_now: bool, now: datetime) -> str:
    best = s.best_item()
    others = [i for i in sorted(s.items, key=lambda i: (i.tier, i.when)) if i is not best][:6]
    support = "\n".join(f"  - [{i.publisher}]({i.url}) · {i.source_type} · {_ago(i.published_at, now)}"
                        for i in others) or "  - none yet (single source)"
    e, d = s.editorial, s.desk
    flag = "🚨 **POST NOW** · " if post_now else ""
    game = d.get("game_name") or "General gaming"
    franchise = f" · franchise: {d['franchise']}" if d.get("franchise") else ""
    return f"""### {rank}. {flag}{s.headline}
**{TYPE_TEXT.get(d.get('bucket'), '')}** · **{game}**{franchise} · {BADGE[s.verification_status]}
**Hot {s.rank_score:.0f}** · opportunity {s.opportunity:.0f} · viral {s.viral:.0f} · significance {_pct(s, 'significance'):.0f} · freshness {s.freshness:.2f} · momentum {d.get('momentum', 0):.0f} · saturation {_sat(s.saturation)} · confidence {d.get('recommendation_confidence', 0):.0f}

- **What happened:** {s.summary}
- **Why it matters:** {e.get('why_care', '')}
- **Why now:** {d.get('why_now', '')}
- **Published / first discovered:** {_ago(s.published_at, now)} / {_ago(s.first_seen_at, now)}
- **Primary source:** [{best.publisher}]({best.url}) ({best.source_type}, tier {best.tier})
- **Supporting sources:**
{support}
- **Category:** {s.content_cluster.replace('_', ' ')} · **Best format:** {e.get('format', '')}
- **Angle:** {e.get('angle', '')}
- **Pitch:** "{e.get('hook', '')}"
- **Risk / caveat:** {e.get('risk', '')}
- <sub>Scored by: {s.judged_by} · {s.reasoning} · story #{s.id}</sub>
"""


def hot_table(hot: list[tuple[Story, bool]], now: datetime) -> list[str]:
    out = ["| # | Game | Story | Type | Label | Hot | Opp | Sig | Fresh | Mom | Sat | Published |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, (s, p) in enumerate(hot, 1):
        d = s.desk
        out.append(f"| {n}{' 🚨' if p else ''} | {d.get('game_name') or 'General'} | {s.headline[:70].replace('|', '/')} | "
                   f"{TYPE_TEXT.get(d.get('bucket'), '')} | {_label(s)} | {s.rank_score:.0f} | {s.opportunity:.0f} | "
                   f"{_pct(s, 'significance'):.0f} | {s.freshness:.2f} | {d.get('momentum', 0):.0f} | {s.saturation:.0f} | "
                   f"{_ago(s.published_at, now).split('(')[-1].rstrip(')')} |")
    return out + [""]


def render(recs: list[tuple[Story, bool]], held: list[Story], stats: dict, now: datetime,
           view: dict | None = None) -> str:
    view = view or {"hot": [s for s, _ in recs], "radar": [], "skipped": [], "angles": {}}
    count = len(recs)
    target = stats.get("hot_list_count", 10)
    lines = [f"# Leonida Desk · Daily Hot List · {now:%A %d %B %Y, %H:%M} UTC", "",
             "_The hottest stories in GTA VI and gaming right now, ranked._", "",
             "> Labels are evidence-based. Anything below 🟢 CONFIRMED must be framed as such wherever it is used. "
             "A short list is a valid result: the list is never padded.", ""]
    if stats.get("warnings"):
        lines += ["**⚠️ Run warnings:** " + " · ".join(stats["warnings"]), ""]
    lines += [f"## 🔥 TOP {target} HOT STORIES", ""]
    if not recs:
        lines += [f"**{NO_HOT}**", "", "_Nothing is both fresh enough and sourced well enough. See On the radar and Skipped._", ""]
    else:
        if count < target:
            lines += [f"_Only {count} stories are hot and sourced well enough today. The list is not padded._", ""]
        lines += hot_table(recs, now)
        lines += ["<sub>Hot = opportunity × (1 − 0.35 × saturation/100) + flagship bonus − topic penalty. "
                  "Sig = significance, judged. 🚨 POST NOW = fresh, credible and not yet crowded.</sub>", ""]
        lines += [story_block(i, s, p, now) for i, (s, p) in enumerate(recs, 1)]
    radar = view.get("radar", [])
    if radar:
        lines += ["## 📡 On the radar", "", "_The next stories down. Not padded into the list above._", ""]
        lines += [f"- {d.get('game_name') or 'General'} · {s.headline[:100]} · {BADGE[s.verification_status]} · "
                  f"hot {s.rank_score:.0f} · fresh {s.freshness:.2f} · [{s.best_item().publisher}]({s.best_item().url}) · story #{s.id}"
                  for s in radar for d in [s.desk]]
        lines.append("")
    if view.get("angles"):
        lines += ["## ↪ More angles on stories already listed", "",
                  "_The same story told twice, or one interview, announcement or running topic capped so it cannot "
                  "fill the list. Use `/ideas <story id>` to develop one._", ""]
    for event, extra in (view.get("angles") or {}).items():
        name = event if event.startswith("same story: ") else event.split(':', 1)[-1].replace('-', ' ').replace('_', ' ')
        lines += [f"- **{name}**: " + "; ".join(
            f"#{s.id} {s.headline[:70]}" for s in extra[:5]) + (f"; and {len(extra) - 5} more" if len(extra) > 5 else "")]
    if view.get("angles"):
        lines.append("")
    skipped = view.get("skipped", [])
    if skipped:
        lines += ["## 🚫 Skipped", "", f"{len(skipped)} ranked stories were not hot or not sourced well enough. Top of the list:", ""]
        lines += [f"- {s.headline[:100]} · {BADGE[s.verification_status]} · _{s.desk.get('skip', '')}_" for s in skipped[:8]]
        lines.append("")
    tech = [s for s in held if s.held_back_reason == TECH_REASON and s.freshness >= 0.15]
    if tech:
        pubs = lambda s: len({i.publisher for i in s.items if i.tier <= 2})
        tech.sort(key=lambda s: (pubs(s), s.freshness), reverse=True)
        lines += ["## 🔌 Product and tech news", "",
                  "_Gadgets and software. Not scored or ranked with gaming. "
                  "Ordered by how many credible outlets carry the story, then by freshness._", ""]
        lines += [f"- #{s.id} · {BADGE[s.verification_status]} · {pubs(s)} outlet(s) · {s.best_item().publisher} · "
                  f"{s.event_time:%d %b %H:%M} · {s.headline[:110]}" for s in tech[:12]]
        lines.append("")
    shown = [s for s in held if s.held_back_reason and s.held_back_reason not in ("stale", CHATTER_REASON, TECH_REASON)
             and not s.held_back_reason.startswith(("not a gaming story", "low-value page"))]
    scope = [s for s in held if (s.held_back_reason or "").startswith(("not a gaming story", "low-value page", "unrelated items"))]
    if scope:
        lines += ["## Filtered out", "", f"{len(scope)} stored stories are out of scope and were not ranked. Most recent:", ""]
        lines += [f"- {s.headline[:100]} — _{s.held_back_reason}_"
                  for s in sorted(scope, key=lambda s: s.event_time, reverse=True)[:8]]
        lines.append("")
    if shown:
        lines += ["## Held back", ""]
        lines += [f"- {s.headline} — _{s.held_back_reason}_" for s in shown][:15]
        lines.append("")
    d, n, cl = stats.get("discovery", {}), stats.get("normalise", {}), stats.get("cluster", {})
    lines += ["## Run diagnostics", "",
              f"- Feeds OK: {len(d.get('feeds_ok', []))} · failed: {len(d.get('feeds_failed', {}))} "
              f"· skipped: {len(d.get('feeds_skipped', []))} · web search: {d.get('web_search')}",
              f"- Items: {n.get('raw', 0)} raw → {n.get('new', 0)} new "
              f"(irrelevant {n.get('irrelevant', 0)}, not gaming {n.get('not_gaming', 0)}, low value {n.get('low_value', 0)}, "
              f"too old {n.get('too_old', 0)}, already known {n.get('known', 0)})",
              f"- Clustering: {cl.get('attached', 0)} items attached to existing stories · "
              f"{cl.get('created', 0)} new stories · {cl.get('merged', 0)} duplicate stories merged "
              f"({cl.get('llm_merged', 0)} by Claude) · {len(cl.get('probable_duplicates', []))} probable "
              f"duplicates unresolved",
              f"- Editorial judgement: {stats.get('judged', 0)} stories by Claude, rest heuristic", ""]
    for fid, err in d.get("feeds_failed", {}).items():
        lines.append(f"  - ✗ `{fid}`: {err}")
    lines += ["", *duplicate_diagnostics(cl), *community_diagnostics(stats.get("community", {}))]
    return "\n".join(lines) + "\n"


def duplicate_diagnostics(cl: dict, limit: int = 12) -> list[str]:
    """Which stories were merged this run, and which look like duplicates but were left alone."""
    merges, probable = cl.get("merges", []), cl.get("probable_duplicates", [])
    lines = ["### Duplicate clusters", ""]
    if not merges and not probable:
        return lines + ["_No duplicate stories found this run._", ""]
    groups: dict[str, list[dict]] = {}
    for m in merges:
        groups.setdefault(m["into"], []).append(m)
    lines.append(f"**Merged this run:** {len(merges)} stories folded into {len(groups)}")
    for into, ms in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:limit]:
        lines.append(f"- **{into}** absorbed {len(ms)}: " + "; ".join(m["absorbed"] for m in ms[:4])
                     + (f"; and {len(ms) - 4} more" if len(ms) > 4 else ""))
    if len(groups) > limit:
        lines.append(f"- and {len(groups) - limit} more groups")
    lines += ["", f"**Probable duplicates left unmerged:** {len(probable)}"
              + (" (borderline; not confident enough to merge without Claude)" if probable else "")]
    lines += [f"- {p['a']} ⇄ {p['b']} · _{p['why']}_" for p in probable[:limit]]
    if len(probable) > limit:
        lines.append(f"- and {len(probable) - limit} more pairs")
    return lines + [""]


def community_diagnostics(cm: dict) -> list[str]:
    """Counts of community posts by content type, and what the classifier changed."""
    if not cm:
        return []
    lines = ["### Reddit / community classification", ""]
    by, new = cm.get("by_type", {}), cm.get("new_by_type", {})
    if by:
        lines.append("- Posts by type (new this run in brackets): " + " · ".join(
            f"{t} {c} ({new.get(t, 0)})" for t, c in sorted(by.items(), key=lambda kv: -kv[1])))
    trans = cm.get("transitions", {})
    if trans:
        lines.append(f"- Stories relabelled this run ({cm.get('community_stories_relabelled', 0)} community-only): "
                     + " · ".join(f"{k}: {v}" for k, v in sorted(trans.items(), key=lambda kv: -kv[1])))
    lines.append(f"- Held as community chatter (demand signal only, not recommended): {cm.get('held_as_chatter', 0)}")
    for h in cm.get("top_chatter", []):
        lines.append(f"  - {h}")
    return lines + [""]


def _row(s: Story) -> dict:
    return {"story_id": s.id, "headline": s.headline, "summary": s.summary,
            "verification_status": s.verification_status, "content_cluster": s.content_cluster,
            "hot_score": s.rank_score, "rank_score": s.rank_score, "opportunity_score": s.opportunity,
            "viral_score": s.viral, "saturation_score": s.saturation, "freshness": s.freshness, "dims": s.dims,
            "editorial": s.editorial, **s.desk, "published_at": str(s.published_at),
            "first_seen_at": str(s.first_seen_at), "judged_by": s.judged_by,
            "sources": [{"publisher": i.publisher, "url": i.url, "type": i.source_type,
                         "tier": i.tier, "published_at": str(i.published_at)} for i in s.items]}


def to_json(recs: list[tuple[Story, bool]], now: datetime, view: dict | None = None) -> str:
    view = view or {}
    return json.dumps({"generated_at": now.isoformat(),
                       "recommendations": [{"rank": n, "post_now": p, **_row(s)} for n, (s, p) in enumerate(recs, 1)],
                       "radar": [_row(s) for s in view.get("radar", [])],
                       "skipped": [{"story_id": s.id, "headline": s.headline, "reason": s.desk.get("skip"),
                                    "hot_score": s.rank_score, "freshness": s.freshness,
                                    "verification_status": s.verification_status, "game": s.desk.get("game")}
                                   for s in view.get("skipped", [])[:40]],
                       "angles": {k: [{"story_id": s.id, "headline": s.headline} for s in v]
                                  for k, v in (view.get("angles") or {}).items()}}, indent=2, default=str)
