"""Claude editorial judgement. Optional: everything degrades to heuristics without an API key.

Guardrails enforced in code after every call:
  - labels are clipped to the evidence ceiling (verify.clip)
  - summaries must come only from supplied source material (prompted) and the report always
    shows the label next to the hook
  - non-confirmed hooks without hedging language get an [UNCONFIRMED] prefix
"""
from __future__ import annotations

import json
import os
import re

from .models import LABELS, Story
from .verify import ceiling, clip, evidence

JUDGED = ["significance", "curiosity_gap", "surprise", "emotional_reaction", "shareability",
          "comment_potential"]
HEDGES = ["rumour", "rumor", "reportedly", "leak", "theory", "unconfirmed", "claim", "might", "could",
          "allegedly", "?", "spotted", "fans have", "fans spot", "fake", "debunk", "fans think", "is it true", "not confirmed", "report"]


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _call(cfg: dict, system: str, user: str) -> str:
    import anthropic
    llm = cfg["settings"]["llm"]
    # Streamed: a long non-streaming reply can sit idle long enough for the connection to be dropped.
    for attempt in (1, 2):
        try:
            with anthropic.Anthropic().messages.stream(
                    model=llm["model"], max_tokens=llm["max_tokens"], system=system,
                    messages=[{"role": "user", "content": user}]) as stream:
                return stream.get_final_text()
        except anthropic.APIConnectionError:
            if attempt == 2:
                raise


def _parse_json(text: str):
    text = re.sub(r"```(?:json)?", "", text).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON in response")
    try:
        return json.loads(text[start:text.rfind("]" if text[start] == "[" else "}") + 1])
    except ValueError:
        if text[start] != "[":
            raise
    # A reply cut off mid-array (output limit): keep every complete object before the cut
    end = len(text)
    while (end := text.rfind("}", start, end)) > 0:
        try:
            return json.loads(text[start:end + 1] + "]")
        except ValueError:
            continue
    raise ValueError("no complete JSON object in response")


# ---------------------------------------------------------------- borderline dedup
def adjudicate_pairs(cfg: dict, pairs) -> list[bool]:
    payload = [{"pair": n, "a": {"title": it.title, "snippet": it.snippet[:300]},
                "b": [{"title": i.title, "snippet": i.snippet[:200]} for i in st.items[:3]]}
               for n, (it, st, _) in enumerate(pairs[:30])]
    system = ("You deduplicate news. Two items are the SAME story only if they report the same underlying "
              "event or discovery (different outlets/wording is fine). Related-but-different events "
              "(e.g. Trailer 2 vs Trailer 3, a rumour vs its later confirmation of something else) are "
              "NOT the same. Reply with JSON only: [{\"pair\": n, \"same\": true|false}].")
    try:
        out = {d["pair"]: bool(d["same"]) for d in _parse_json(_call(cfg, system, json.dumps(payload)))}
    except Exception:
        return [False] * len(pairs)
    return [out.get(n, False) for n in range(len(pairs))]


# ---------------------------------------------------------------- editorial judgement
SYSTEM_EDITORIAL = """You are the research desk of Leonida Desk, a gaming news desk briefing an Editor-in-Chief.
The job is to find the HOTTEST stories in games right now (Grand Theft Auto VI first, then gaming
broadly) and to rank them honestly: what is new, what matters, what people are talking about.
For each story you receive its source items (publisher, type, tier, title, snippet, url) and the
system's verification ceiling.

HARD RULES
- Use ONLY the supplied items. Do not add facts, numbers, names, dates or quotes that are not in them.
- Never present a rumour, theory or community discovery as confirmed. The label must not exceed the
  ceiling. If unsure, choose the lower-confidence label.
- Headlines and hooks for anything below CONFIRMED must be hedged (e.g. "reportedly", "a leak claims",
  "fans think").
- No fake quotes. No clickbait the story cannot deliver.
- Category must be one of the provided category slugs.
- Score honestly and use the whole range. Most stories are 3-6. Give 8+ only for genuinely big news.

Score these 0-10: significance (how much this matters to players or the games industry: a release
date, delay, price, acquisition, closure or major reveal is high; a minor patch, a sale or a promo is
low), curiosity_gap, surprise, emotional_reaction, shareability, comment_potential.

Reply with a JSON array only, one object per story:
{"id": str, "headline": neutral factual headline, "summary": 1-2 sentences of what happened,
 "scope": "game" if the story is about a video game, its makers, its players or game hardware;
   "not_game" if it is film, TV, celebrity or general entertainment coverage that merely mentions a
   game or franchise; "low_value" if it is a listicle, roundup, deal, guide or review with no single
   story in it; "mixed" if the items are clearly about two unrelated subjects,
 "game": the game the story is about, named exactly as the items name it, or null,
 "category": slug, "label": one of the labels, "scores": {...six scores...},
 "why_care": one sentence on why readers would care,
 "format": the best way to cover it (news brief, explainer, analysis, fact check, timeline),
 "angle": the original editorial angle, not a restatement of the headline,
 "hook": a one-line pitch for the story (<=14 words, hedged when below CONFIRMED),
 "risk": the main caveat/risk,
 "conflict": if the items contradict each other on a material fact, one sentence saying how; else null,
 "reasoning": one sentence on why this story is or isn't hot right now,
 "why_now": one sentence on why today rather than next week, from the items only,
 "parent_event": if two or more stories in this batch are different angles on ONE interview, cover
   story, showcase or announcement, give them the same short kebab-case key
   (e.g. "love-magazine-rockstar-interview"); otherwise null}"""


def editorial(cfg: dict, stories: list[Story]) -> int:
    """Fill dims/editorial for the given stories in place. Returns count judged."""
    if not stories:
        return 0
    cats = list(cfg["categories"]["categories"])
    payload = {"labels": LABELS, "categories": cats, "stories": []}
    for s in stories:
        payload["stories"].append({
            "id": str(id(s)), "ceiling": ceiling(evidence(s, cfg)), "current_label": s.verification_status,
            "items": [{"publisher": i.publisher, "type": i.source_type, "tier": i.tier, "title": i.title,
                       "snippet": i.snippet[:400], "url": i.url, "published": str(i.published_at)}
                      for i in sorted(s.items, key=lambda i: i.tier)[:6]]})
    try:
        results = _parse_json(_call(cfg, SYSTEM_EDITORIAL, json.dumps(payload, default=str)))
    except Exception as exc:
        print(f"  ! editorial LLM call failed ({type(exc).__name__}); using heuristics")
        return 0
    by_id = {str(id(s)): s for s in stories}
    n = 0
    for r in results:
        s = by_id.get(str(r.get("id")))
        if not s:
            continue
        ev = evidence(s, cfg)
        s.verification_status = clip(r.get("label", s.verification_status), ev, s.verification_status)
        if r.get("category") in cats:
            s.content_cluster = r["category"]
        if r.get("headline"):
            s.headline = r["headline"].strip()
        s.summary = (r.get("summary") or s.summary).strip()
        for d in JUDGED:
            try:
                s.dims[d] = max(0.0, min(1.0, float(r.get("scores", {}).get(d, 5)) / 10))
            except (TypeError, ValueError):
                pass
        s.editorial = {k: (r.get(k) or "").strip() for k in ("why_care", "format", "angle", "hook", "risk",
                                                             "conflict")}
        if r.get("scope") in ("not_game", "low_value", "mixed"):
            s.desk["out_of_scope"] = {"not_game": "not_gaming", "low_value": "low_value",
                                      "mixed": "unrelated items were clustered together: needs splitting before use"}[r["scope"]]
        if r.get("game") and not s.desk.get("game"):
            s.desk["game_name"] = str(r["game"]).strip()[:40]
        s.reasoning = (r.get("reasoning") or "").strip()
        if r.get("why_now"):
            s.editorial["why_now"] = str(r["why_now"]).strip()
        if r.get("parent_event"):
            s.desk["parent_event"] = f"{s.desk.get('game') or 'general'}:{str(r['parent_event']).strip().lower()}"
        s.judged_by = "claude"
        n += 1
    return n


def enforce_hook_hedging(s: Story) -> None:
    hook = s.editorial.get("hook", "")
    if hook and s.verification_status not in ("CONFIRMED", "HIGH_CONFIDENCE_REPORT"):
        if not any(h in hook.lower() for h in HEDGES):
            s.editorial["hook"] = f"[UNCONFIRMED] {hook}"
