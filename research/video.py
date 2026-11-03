"""SHORT-FORM VIDEO: production packages for /make.

A package is the complete plan for one short: angle, hooks, voiceover, storyboard, a generation
prompt per shot, captions and sources. It is built from the same evidence packet as the article, so
research is done once. The checks here are deterministic. Nothing here generates or posts a video.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .articles import _QUOTE, _UPGRADE, iso, load_packet, now_utc, slugify
from .config import resolve
from .desk import label_at_least
from .models import CONFIDENCE_ORDER
from .text import tokens

STATUSES = ["IDEA", "SCRIPTED", "READY_FOR_GENERATION", "GENERATING", "READY_FOR_REVIEW", "APPROVED", "PUBLISHED",
            "REJECTED"]
WRITING = ("IDEA", "SCRIPTED", "READY_FOR_GENERATION", "DRAFT")      # statuses the checker may move between
REQUIRED = ["video_id", "story_id", "evidence_packet", "verification_status", "treatment", "editorial_angle",
            "entertainment_angle", "money_shot", "visual_premise", "visual_escalation", "visual_payoff",
            "hooks", "recommended_hook", "hook_style", "ending_hook", "retention_edit", "viewer_test",
            "voiceover", "shots", "editing_notes", "sound_music", "cta",
            "youtube_title", "youtube_description", "tiktok_caption", "instagram_caption", "sources"]
SHOT_FIELDS = ["seconds", "shot_type", "camera", "visual", "on_screen_text"]
ANGLE_KEYS = ["surprising_fact", "entertaining_consequence", "visual_opportunity", "relatable_scenario",
              "wait_what_moment", "why_viewers_care"]
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_LEGACY_SOURCE = {"generated": "AI_VIDEO", "typography": "TEXT_GRAPHIC", "own_capture": "OTHER"}
_HEDGE = re.compile(r"\b(reported(ly)?|report|rumou?r(ed)?|claims?|claimed|theory|fans? think|unconfirmed|could|may|"
                    r"might|leak(ed)?|suggests?|appears?|according to|says|said|told|imagine|what if|if)\b", re.I)
_FOOTAGE = re.compile(r"\b(gameplay|game footage|trailer footage|screenshot|screen ?grab|official (art|footage)|logo)\b", re.I)


def videos_dir(cfg: dict) -> Path:
    return resolve(cfg, cfg["publishing"].get("videos_dir") or cfg["publishing"]["video"].get("videos_dir", "outputs/videos"))


def asset_type(shot: dict) -> str | None:
    """A shot's asset type. Packages written before asset types existed carry `source` instead."""
    return shot.get("asset_type") or _LEGACY_SOURCE.get(shot.get("source"), shot.get("source"))


def is_generated(shot: dict, cfg: dict) -> bool:
    return asset_type(shot) in cfg["publishing"]["video"]["generated_asset_types"] and not shot.get("reuse_shot")


def set_status(pkg: dict, status: str, note: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if pkg.get("status") != status:
        pkg.setdefault("history", []).append({"status": status, "at": iso(now_utc()), "note": note})
    pkg["status"] = status


def new_package(story_id: int, packet: dict, cfg: dict, game: str | None = None, headline: str = "") -> dict:
    """An empty package for the writer to fill. It inherits the story's label and sources."""
    v = cfg["publishing"]["video"]
    vid = f"{now_utc():%Y%m%d}-{story_id}-{slugify(headline)[:40] or 'short'}"
    return {"video_id": vid, "story_id": story_id, "evidence_packet": packet["packet_id"], "game": game,
            "verification_status": packet["story_label"], "status": "IDEA", "created_at": iso(now_utc()),
            "history": [{"status": "IDEA", "at": iso(now_utc()), "note": "package started"}],
            "format": {"aspect": v["aspect"], "target_seconds": v["seconds"]},
            "treatment": None, "editorial_angle": "",
            # 1. The story as entertainment, not as an article: fill this before anything else
            "entertainment_angle": dict.fromkeys(ANGLE_KEYS, ""),
            # 2. The one visual that stops the scroll. It is shot 1.
            "money_shot": "",
            # Decide what the viewer SEES before writing a word of voiceover
            "visual_premise": "", "visual_escalation": "", "visual_payoff": "", "visual_style": "",
            "hooks": [], "recommended_hook": None, "hook_style": None,
            "voiceover": [], "shots": [], "editing_notes": "", "sound_music": "", "cta": "",
            # The last thing said: a new curiosity, never "follow for part two"
            "ending_hook": "",
            # After the first draft: what was cut, and the scroll test. Filled honestly or not at all.
            "retention_edit": {"cut": [], "seconds_before": None, "seconds_after": None},
            "viewer_test": {},
            "youtube_title": "", "youtube_description": "", "tiktok_caption": "", "instagram_caption": "",
            "sources": [], "disclosure": v["disclosure"],
            "render": {"adapter": v["higgsfield"]["adapter"], "jobs": [], "cost": None}, "posts": []}


def load(video_id: str, cfg: dict) -> tuple[dict, Path]:
    path = videos_dir(cfg) / video_id / "package.json"
    return json.loads(path.read_text()), path


def all_packages(cfg: dict) -> list[dict]:
    d = videos_dir(cfg)
    return [json.loads(p.read_text()) for p in sorted(d.glob("*/package.json"))] if d.exists() else []


def voiceover_text(pkg: dict) -> str:
    return " ".join(line["text"].strip() for line in pkg.get("voiceover", []))


def runtime(pkg: dict) -> float:
    return float(sum(s.get("seconds", 0) for s in pkg.get("shots", [])))


def validate(pkg: dict, packet: dict, cfg: dict) -> list[dict]:
    """Every problem as {level, code, detail}. Errors block READY_FOR_GENERATION."""
    v = cfg["publishing"]["video"]
    issues: list[dict] = []

    def add(level: str, code: str, detail: str) -> None:
        issues.append({"level": level, "code": code, "detail": detail})

    for k in REQUIRED:
        if pkg.get(k) in (None, "", []):
            add("error", "missing", f"{k} is empty")
    if pkg.get("treatment") and pkg["treatment"] not in v["treatments"]:
        add("error", "treatment", f"treatment must be one of {v['treatments']}")
    if pkg.get("hook_style") and pkg["hook_style"] not in v["hook_styles"]:
        add("error", "hooks", f"hook_style must be one of {v['hook_styles']}")
    hooks = pkg.get("hooks") or []
    if len(hooks) != 3 or len({h.strip().lower() for h in hooks}) != 3:
        add("error", "hooks", "exactly three different hook options are required")
    if pkg.get("recommended_hook") not in (0, 1, 2):
        add("error", "hooks", "recommended_hook must be the index (0-2) of one of the hooks")
    elif len(hooks) == 3 and len(hooks[pkg["recommended_hook"]].split()) > v.get("hook_max_words", 12):
        add("warning", "slow_intro", f"the recommended hook is over {v.get('hook_max_words', 12)} words: it will not land in 1-2 seconds")
    issues.extend(retention_issues(pkg, cfg))
    spoken = (" ".join(hooks) + " " + voiceover_text(pkg)).lower()
    for phrase in v.get("weak_phrases", []):
        if phrase in spoken:
            add("warning", "weak_phrase", f"\"{phrase}\" sounds generic or oversold: say the specific thing instead")

    # --- label inheritance and hedging: a video never says more than its story's label allows
    label, story_label = pkg.get("verification_status"), packet.get("story_label")
    if label in CONFIDENCE_ORDER and story_label in CONFIDENCE_ORDER and not label_at_least(story_label, label):
        add("error", "label_upgraded", f"video says {label} but the story is {story_label}")
    public = {"hook": " | ".join(hooks), "youtube_title": pkg.get("youtube_title", ""),
              "tiktok_caption": pkg.get("tiktok_caption", ""), "instagram_caption": pkg.get("instagram_caption", "")}
    if label != "CONFIRMED":
        for name, text in {**public, "voiceover": voiceover_text(pkg)}.items():
            if _UPGRADE.search(text):
                add("error", "rumour_upgraded", f"{name} uses confirmed/official wording for a {label} story")
    if label in CONFIDENCE_ORDER and not label_at_least(label, "HIGH_CONFIDENCE_REPORT"):
        for n, h in enumerate(hooks):
            if not _HEDGE.search(h):
                add("error", "unhedged", f"hook {n + 1} states a {label.replace('_', ' ').lower()} as fact")
        if not _HEDGE.search(pkg.get("youtube_title", "")):
            add("error", "unhedged", "youtube_title is not hedged")

    # --- voiceover: every factual line cites the evidence packet; quotes are verbatim
    claims = {c["id"]: c for c in packet["claims"] if c.get("kind") == "fact"}
    quotes = [c["quote"] for c in packet["claims"] if c.get("quote")]
    norm = lambda t: re.sub(r"\s+", " ", t.replace("’", "'")).strip().lower()
    for n, line in enumerate(pkg.get("voiceover", []), 1):
        kind = line.get("kind", "fact")
        if kind == "fact" and not line.get("claims"):
            add("error", "unsupported_claim", f"voiceover line {n} states a fact with no claim id")
        for cid in line.get("claims", []):
            if cid not in claims:
                add("error", "unknown_citation", f"voiceover line {n} cites {cid}, which is not a verified claim")
        for q in _QUOTE.findall(line.get("text", "")):
            if len(q.split()) >= 4 and not any(norm(q) in norm(k) for k in quotes):
                add("error", "unsupported_quote", f"voiceover line {n} quotes text that is not in the evidence: \"{q[:70]}\"")
    urls = {s["url"] for s in packet["sources"]}
    for s in pkg.get("sources", []):
        if s.get("url") not in urls:
            add("error", "unsourced", f"source not in the evidence packet: {s.get('url')}")

    # --- storyboard
    shots = pkg.get("shots") or []
    if len(shots) < v["min_shots"]:
        add("error", "storyboard", f"needs at least {v['min_shots']} shots (has {len(shots)})")
    banned = _banned_names(cfg)
    lo_s, hi_s = v.get("scene_seconds", [3, 6])
    for n, s in enumerate(shots, 1):
        for f in SHOT_FIELDS:
            if s.get(f) in (None, "") and f != "on_screen_text":
                add("error", "storyboard", f"shot {n} is missing {f}")
        if "on_screen_text" not in s:
            add("error", "storyboard", f"shot {n} has no on_screen_text field (use an empty string for none)")
        kind = asset_type(s)
        if kind not in v["asset_types"]:
            add("error", "footage", f"shot {n} asset_type must be one of {v['asset_types']}")
            continue
        if kind in v["third_party_asset_types"]:
            # Someone else's picture: it must be the stored source itself, and a person clears the rights
            if s.get("asset_url") not in urls:
                add("error", "footage", f"shot {n} uses a {kind} that is not a source in the evidence packet (asset_url)")
            if not s.get("rights_note"):
                add("error", "footage", f"shot {n} uses a {kind} with no rights_note saying why it may be used")
            add("warning", "rights", f"shot {n} uses third-party material ({kind}): the editor must clear it before publishing")
        if not s.get("vo_lines") and n != len(shots):
            add("warning", "storyboard", f"shot {n} is tied to no voiceover line: every scene should move the story forward")
        prompt = s.get("higgsfield_prompt") or ""
        if is_generated(s, cfg):
            if len(prompt.split()) < v["min_prompt_words"]:
                add("error", "prompt", f"shot {n} needs a full generation prompt")
            hit = banned.search(prompt) or _FOOTAGE.search(prompt)
            if hit:
                add("error", "prompt", f"shot {n} prompt names protected or third-party material (\"{hit.group(0)}\"): "
                                       "describe an original scene instead")
            if not lo_s <= s.get("seconds", 0) <= hi_s:
                add("warning", "scene_length", f"shot {n} is {s.get('seconds')}s: generated scenes of {lo_s}-{hi_s}s are cheaper and more reliable")
    if shots and shots[0].get("seconds", 0) > v.get("hook_max_seconds", 3):
        add("warning", "slow_intro", f"the first shot runs {shots[0]['seconds']}s: the hook should land within {v.get('hook_max_seconds', 3)}s")
    total = runtime(pkg)
    lo, hi = v["seconds"]
    if shots and not lo <= total <= hi:
        add("error", "duration", f"runtime is {total:.0f}s; a short must be {lo}-{hi}s")
    words = len(voiceover_text(pkg).split())
    if total and words:
        pace = words / total
        if not v["words_per_second"][0] <= pace <= v["words_per_second"][1]:
            add("error", "duration", f"voiceover is {words} words over {total:.0f}s ({pace:.1f}/s): it will not fit the cut")
    if pkg.get("format", {}).get("aspect") != v["aspect"]:
        add("error", "format", f"aspect must be {v['aspect']}")

    # --- AI disclosure, on screen and in the description
    if cfg.get("design", {}).get("disclosure", {}).get("on_screen"):
        on_screen = " ".join(str(s.get("on_screen_text", "")) for s in shots).lower()
        if "ai-generated" not in on_screen and "ai generated" not in on_screen:
            add("error", "disclosure", "no shot carries an on-screen 'AI-generated' label")
    if "ai-generated" not in pkg.get("youtube_description", "").lower():
        add("error", "disclosure", "youtube_description does not say the visuals are AI-generated")

    # --- not the same template again
    mine = tokens(" ".join(s.get("higgsfield_prompt") or "" for s in shots))
    for other in all_packages(cfg):
        if other["video_id"] == pkg.get("video_id") or other.get("status") == "REJECTED":
            continue
        theirs = tokens(" ".join(s.get("higgsfield_prompt") or "" for s in other.get("shots", [])))
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= v["template_similarity"]:
            add("warning", "template", f"visual prompts are very close to {other['video_id']}: vary the treatment")
    return issues


def retention_issues(pkg: dict, cfg: dict) -> list[dict]:
    """The retention engine's checks on a package: is this written to be watched, not read?
    Deterministic and deliberately blunt. They cannot tell whether a video is good; they can tell
    when it opens like an article, hides its best shot, states a guess as a fact or repeats itself."""
    v, r = cfg["publishing"]["video"], cfg["publishing"]["video"]["retention"]
    out: list[dict] = []

    def add(level: str, code: str, detail: str) -> None:
        out.append({"level": level, "code": code, "detail": detail})

    angle = pkg.get("entertainment_angle") or {}
    for k in ANGLE_KEYS:
        if not str(angle.get(k) or "").strip():
            add("error", "angle", f"entertainment_angle.{k} is empty: find the entertainment in the story before scripting")
    lines, shots = pkg.get("voiceover") or [], pkg.get("shots") or []

    # the money shot opens the video: footage, not a card, not a slow establishing shot
    if shots:
        if asset_type(shots[0]) not in v["generated_asset_types"] + v["third_party_asset_types"]:
            add("error", "money_shot", "shot 1 is a graphic: open on the money shot, the footage that stops the scroll")
        if not shots[0].get("money_shot"):
            add("error", "money_shot", "shot 1 is not marked money_shot: the strongest visual goes first, not halfway through")

    # the first two seconds
    if lines:
        first = _SENTENCE.split(lines[0]["text"].strip())[0]
        low = lines[0]["text"].strip().lower()
        hit = next((b for b in r["banned_openers"] if low.startswith(b)), None)
        if hit:
            add("error", "opener", f"the video opens with \"{hit}...\": start on a consequence, a question, a reaction or a challenge")
        if len(first.split()) > r["opener_max_words"]:
            add("error", "opener", f"the first sentence is {len(first.split())} words: keep it to {r['opener_max_words']} or fewer")

    # written to be heard: short sentences, no article language
    for n, line in enumerate(lines, 1):
        for s in _SENTENCE.split(line["text"].strip()):
            if len(s.split()) > r["sentence_max_words"]:
                add("warning", "article_style", f"voiceover line {n} has a {len(s.split())}-word sentence: one sentence, one idea")
        low = line["text"].lower()
        for w in r["article_words"]:
            if w in low:
                add("warning", "article_style", f"voiceover line {n} says \"{w}\": say it the way a person would")
        # a possibility must sound like one
        if line.get("kind") == "speculation" and not any(w in low for w in r["conditional_words"]):
            add("error", "speculation_as_fact", f"voiceover line {n} is speculation stated as fact: use could, might, imagine or if")
        cap = line.get("caption")
        if cap and len(cap.replace("*", "").replace("/", " ").split()) > r["punch_caption_max_words"]:
            add("warning", "caption", f"the caption on line {n} is {len(cap.split())} words: punch captions are "
                                      f"{r['punch_caption_max_words']} words or fewer, not a transcript")
    if lines and not any(line.get("caption") for line in lines):
        add("warning", "caption", "no voiceover line has a punch caption: captions should sell the idea, not transcribe it")

    # every sentence has a visual, and no shot sits dead
    covered = {ln for s in shots for ln in s.get("vo_lines", [])}
    for n in range(1, len(lines) + 1):
        if n not in covered:
            add("error", "beat_map", f"voiceover line {n} has no shot: decide what the viewer sees while it is said")
    for n, s in enumerate(shots, 1):
        still = not is_generated(s, cfg) and asset_type(s) not in v["third_party_asset_types"]
        still = still and not str((s.get("footage") or {}).get("asset", "")).lower().endswith((".mp4", ".mov", ".webm"))
        if still and s.get("seconds", 0) > r["still_max_seconds"]:
            add("warning", "dead_attention", f"shot {n} holds a graphic or still for {s['seconds']}s: nothing is happening on screen")
        elif s.get("seconds", 0) > r["shot_max_seconds"]:
            add("warning", "dead_attention", f"shot {n} runs {s['seconds']}s: make sure something new happens during it")
        if is_generated(s, cfg) and not str(s.get("purpose") or "").strip():
            add("error", "purpose", f"shot {n} has no purpose: say what happens in it and why the viewer keeps watching")

    # the ending leaves a question open
    if pkg.get("ending_hook") and lines and pkg["ending_hook"].strip().lower() not in lines[-1]["text"].lower():
        add("error", "ending", "ending_hook is not the last thing said: finish on the next curiosity")

    # the retention edit and the scroll test were actually done
    edit = pkg.get("retention_edit") or {}
    if lines and not edit.get("cut") and not edit.get("nothing_to_cut_because"):
        add("error", "retention_edit", "retention_edit.cut is empty: reread the draft and remove what the viewer does not need "
                                       "(or say in nothing_to_cut_because why nothing could go)")
    test = pkg.get("viewer_test") or {}
    for q in r["viewer_test"]:
        a = test.get(q)
        if not isinstance(a, dict) or "pass" not in a:
            add("error", "viewer_test", f"viewer_test.{q} is unanswered")
        elif not a["pass"]:
            add("error", "viewer_test", f"viewer_test.{q} is a no ({a.get('note', 'no note')}): rework before generating")

    # the channel has a personality; the videos are not copies
    earlier = sorted((p for p in all_packages(cfg) if p.get("video_id") != pkg.get("video_id") and p.get("status") != "REJECTED"
                      and p.get("created_at", "") < pkg.get("created_at", "~")), key=lambda p: p.get("created_at", ""))
    if earlier and pkg.get("hook_style") and earlier[-1].get("hook_style") == pkg["hook_style"]:
        add("warning", "repetition", f"the previous video also used a {pkg['hook_style']} hook: rotate the style")
    said = voiceover_text(pkg).lower()
    for phrase in r["micro_hooks"]:
        if phrase in said and any(phrase in voiceover_text(p).lower() for p in earlier[-3:]):
            add("warning", "repetition", f"\"{phrase}\" was used in a recent video: find another way to turn the corner")
    return out


def _banned_names(cfg: dict) -> re.Pattern:
    names = {"rockstar", "take-two", "nintendo", "playstation", "xbox"}
    for g in cfg["games"]["games"].values():
        names.update(a.lower() for a in g.get("aliases") or [])
        names.update(x.lower() for x in (g.get("name"), g.get("franchise"), g.get("developer")) if x)
    names.discard("leonida")
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b", re.I)


def _timed_shots(pkg: dict):
    t0 = 0.0
    for n, s in enumerate(pkg.get("shots", []), 1):
        yield n, t0, s
        t0 += s.get("seconds", 0)


def render_markdown(pkg: dict) -> str:
    """The package as one readable document, in the order a producer works through it."""
    out = [f"# {pkg['youtube_title'] or pkg['video_id']}", "",
           f"`{pkg['video_id']}` · story #{pkg['story_id']} · {pkg.get('game') or 'General gaming'} · "
           f"{pkg['verification_status'].replace('_', ' ')} · status {pkg['status']} · "
           f"{pkg['format']['aspect']} · {runtime(pkg):.0f}s · treatment: {pkg.get('treatment')}", "",
           "## Editorial angle", "", pkg["editorial_angle"], "",
           "## What the viewer sees", "", f"- **Visual premise:** {pkg.get('visual_premise', '')}",
           f"- **Visual escalation:** {pkg.get('visual_escalation', '')}",
           f"- **Visual payoff:** {pkg.get('visual_payoff', '')}", "", "## Hook options", ""]
    out += [f"{n + 1}. {h}" + ("  **← recommended**" if n == pkg.get("recommended_hook") else "") for n, h in enumerate(pkg["hooks"])]
    out += ["", f"_Hook style: {pkg.get('hook_style')}._", "", "## Full voiceover", ""]
    out += [f"{n}. {line['text']}" + (f"  `[{', '.join(line['claims'])}]`" if line.get("claims") else "  `[framing]`")
            for n, line in enumerate(pkg["voiceover"], 1)]
    out += ["", f"_{len(voiceover_text(pkg).split())} words._", "", "## Storyboard", ""]
    for n, t0, s in _timed_shots(pkg):
        out += [f"### Shot {n} · {t0:.0f}-{t0 + s['seconds']:.0f}s · {s['seconds']}s · {s['shot_type']}", "",
                f"- **Asset type:** {asset_type(s)}" + (f" (reuses shot {s['reuse_shot']})" if s.get("reuse_shot") else ""),
                f"- **Camera / motion:** {s['camera']}", f"- **Visual:** {s['visual']}",
                f"- **On-screen text:** {s.get('on_screen_text') or 'none'}",
                f"- **Voiceover lines:** {', '.join(str(x) for x in s.get('vo_lines', [])) or 'none'}"]
        if s.get("higgsfield_prompt"):
            out += ["- **Higgsfield prompt:**", "", f"  > {s['higgsfield_prompt']}"]
        out.append("")
    out += ["## Editing notes", "", pkg["editing_notes"], "", "## Sound and music", "", pkg["sound_music"], "",
            "## CTA", "", pkg["cta"], "", "## YouTube Shorts title", "", pkg["youtube_title"], "",
            "## YouTube description", "", pkg["youtube_description"], "", "## TikTok caption", "", pkg["tiktok_caption"], "",
            "## Instagram caption", "", pkg["instagram_caption"], "", "## Sources and evidence", ""]
    out += [f"- [{s['name']}]({s['url']})" for s in pkg["sources"]]
    out += ["", f"_{pkg.get('disclosure', '')}_", ""]
    return "\n".join(out)


def prompts(pkg: dict, cfg: dict) -> list[dict]:
    """One entry per shot that needs a generation, as /render reads it."""
    return [{"shot": n, "asset_type": asset_type(s), "seconds": s["seconds"], "aspect": pkg["format"]["aspect"],
             "camera": s.get("camera"), "prompt": s.get("higgsfield_prompt"),
             "method": "text_to_video" if asset_type(s) == "AI_VIDEO" else "text_to_image+image_to_video"}
            for n, _, s in _timed_shots(pkg) if is_generated(s, cfg)]


def export(pkg: dict, packet: dict, d: Path, cfg: dict, issues: list[dict]) -> None:
    """Write the project files a producer works from. package.json is the source; these are views of it."""
    j = lambda name, data: (d / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    (d / "assets").mkdir(exist_ok=True)
    desk = pkg.get("desk") or {}
    brief = [f"# Brief · {pkg['video_id']}", "",
             f"Story #{pkg['story_id']} · {pkg.get('game') or 'General gaming'} · {pkg['verification_status'].replace('_', ' ')} · "
             f"{pkg.get('treatment')} · {pkg['format']['aspect']} · {runtime(pkg):.0f}s · status {pkg['status']}", "",
             "## Editorial angle", "", pkg.get("editorial_angle", ""), "",
             "## Entertainment angle", "", *[f"- {k.replace('_', ' ').capitalize()}: {(pkg.get('entertainment_angle') or {}).get(k, '')}"
                                             for k in ANGLE_KEYS], "",
             f"**Money shot (shot 1):** {pkg.get('money_shot', '')}", "", f"**Ending hook:** {pkg.get('ending_hook', '')}", "",
             "## What the viewer sees", "",
             f"- Premise: {pkg.get('visual_premise', '')}", f"- Escalation: {pkg.get('visual_escalation', '')}",
             f"- Payoff: {pkg.get('visual_payoff', '')}", f"- Visual style: {pkg.get('visual_style', '')}", "", "## Hooks", ""]
    brief += [f"{n + 1}. {h}" + (" (recommended)" if n == pkg.get("recommended_hook") else "") for n, h in enumerate(pkg.get("hooks", []))]
    if desk:
        brief += ["", "## Why this story", "", f"Desk tier when started: **{desk.get('tier')}** · {desk.get('tier_reason', '')}", ""]
        for tier, checks in (desk.get("gate") or {}).items():
            brief += [f"**{tier} checks**", ""] + [f"- {'PASS' if c['ok'] else 'MISS'} · {c['check']}: {c['value']} (needs {c['bar']})"
                                                  for c in checks] + [""]
    brief += ["## Checker", ""] + ([f"- {i['level'].upper()} {i['code']}: {i['detail']}" for i in issues] or ["- no issues"]) + [""]
    (d / "brief.md").write_text("\n".join(brief))
    script = [f"# Script · {pkg['video_id']}", "", f"{len(voiceover_text(pkg).split())} words · {runtime(pkg):.0f}s", ""]
    by_line: dict[int, str] = {}
    for n, t0, s in _timed_shots(pkg):
        for ln in s.get("vo_lines", []):
            by_line.setdefault(ln, f"{t0:.0f}s")
    script += [f"{n}. [{by_line.get(n, '?')}] {line['text']}  " + (f"`{', '.join(line['claims'])}`" if line.get("claims") else "`framing`")
               for n, line in enumerate(pkg.get("voiceover", []), 1)]
    script += ["", "## Editing notes", "", pkg.get("editing_notes", ""), "", "## Sound and music", "", pkg.get("sound_music", ""),
               "", "## CTA", "", pkg.get("cta", ""), ""]
    (d / "script.md").write_text("\n".join(script))
    j("storyboard.json", [{"shot": n, "start": t0, "end": t0 + s.get("seconds", 0), **s, "asset_type": asset_type(s)}
                          for n, t0, s in _timed_shots(pkg)])
    j("higgsfield-prompts.json", prompts(pkg, cfg))
    used = {c for line in pkg.get("voiceover", []) for c in line.get("claims", [])}
    j("evidence.json", {"packet": packet["packet_id"], "story_label": packet["story_label"],
                        "claims": [c for c in packet["claims"] if c["id"] in used],
                        "sources": [s for s in packet["sources"] if s["url"] in {x.get("url") for x in pkg.get("sources", [])}],
                        "conflicts": packet.get("conflicts", [])})
    (d / "social-copy.md").write_text("\n".join([
        f"# Social copy · {pkg['video_id']}", "", "## YouTube Shorts title", "", pkg.get("youtube_title", ""), "",
        "## YouTube description", "", pkg.get("youtube_description", ""), "", "## TikTok caption", "", pkg.get("tiktok_caption", ""), "",
        "## Instagram caption", "", pkg.get("instagram_caption", ""), "", "## Sources", "",
        *[f"- {s['name']}: {s['url']}" for s in pkg.get("sources", [])], ""]))
    j("status.json", {"video_id": pkg["video_id"], "status": pkg["status"], "updated_at": pkg.get("updated_at"),
                      "history": pkg.get("history", []), "render": pkg.get("render", {}), "posts": pkg.get("posts", []),
                      "errors": sum(i["level"] == "error" for i in issues), "warnings": sum(i["level"] == "warning" for i in issues)})


def save(pkg: dict, cfg: dict) -> tuple[Path, list[dict]]:
    """Validate, set the status, and write package.json, package.md and the project files."""
    packet = load_packet(pkg["evidence_packet"], cfg)
    issues = validate(pkg, packet, cfg)
    errors = [i for i in issues if i["level"] == "error"]
    if pkg.get("status") in WRITING:
        started = bool(pkg.get("voiceover") and pkg.get("shots"))
        set_status(pkg, "IDEA" if not started else "SCRIPTED" if errors else "READY_FOR_GENERATION",
                   f"checker: {len(errors)} errors")
    pkg["updated_at"] = iso(now_utc())
    d = videos_dir(cfg) / pkg["video_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "package.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n")
    (d / "package.md").write_text(render_markdown(pkg))
    export(pkg, packet, d, cfg, issues)
    return d / "package.md", issues
