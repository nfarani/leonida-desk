"""Higgsfield generation for /render.

Two paths, chosen by config/publishing.yaml -> video.higgsfield.adapter:

  manual  writes generation_sheet.md for a person to run in the Higgsfield app; finished clips are
          dropped into the package's assets/ folder and picked up by `ingest`.
  api     submits each generated shot to the Higgsfield API, stores the job ids, polls, downloads.

The API lifecycle is the one in docs.higgsfield.ai: POST to the model's path with
"Authorization: Key <id>:<secret>", keep request_id and status_url, poll status_url until the
status is completed / failed / nsfw / canceled, then download video.url (or images[0].url).
Model paths, parameters and prices differ per model and are NOT in this file: they are read from
config, where the operator copies them from the Higgsfield console. Nothing is ever submitted
without an explicit confirmation, because every submission spends credits.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .articles import iso, now_utc
from .video import asset_type, is_generated, runtime, set_status

LIVE = ("queued", "in_progress")
DONE = "completed"
EXT = (".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp")
STEPS = {"AI_VIDEO": ["text_to_video"], "AI_IMAGE_WITH_MOTION": ["text_to_image", "image_to_video"]}


def _hf(cfg: dict) -> dict:
    return cfg["publishing"]["video"]["higgsfield"]


def plan(pkg: dict, cfg: dict) -> dict:
    """What generating this package involves: scenes, generations, model per step, estimated cost.
    The cost is only as good as cost_per_generation in config; unknown prices stay unknown."""
    models, rows, total, unknown = _hf(cfg)["models"], [], 0.0, False
    for n, s in enumerate(pkg["shots"], 1):
        if not is_generated(s, cfg):
            continue
        for step in STEPS[asset_type(s)]:
            m = models.get(step) or {}
            cost = m.get("cost_per_generation")
            unknown |= cost is None
            total += cost or 0
            rows.append({"shot": n, "step": step, "seconds": s["seconds"], "model": m.get("name") or m.get("path"),
                         "configured": bool(m.get("path")), "cost": cost})
    return {"scenes": len(pkg["shots"]), "generated_scenes": len({r["shot"] for r in rows}), "generations": len(rows),
            "rows": rows, "estimated_cost": None if unknown else round(total, 2), "cost_unit": _hf(cfg).get("cost_unit", "credits"),
            "not_generated": [(n, asset_type(s)) for n, s in enumerate(pkg["shots"], 1) if not is_generated(s, cfg)]}


def plan_text(pkg: dict, cfg: dict) -> str:
    p = plan(pkg, cfg)
    cost = f"{p['estimated_cost']} {p['cost_unit']}" if p["estimated_cost"] is not None else \
        "unknown (set cost_per_generation in config/publishing.yaml from the Higgsfield console)"
    lines = [f"Generation plan · {pkg['video_id']} · {runtime(pkg):.0f}s · {pkg['format']['aspect']}",
             f"  scenes: {p['scenes']} · scenes needing generation: {p['generated_scenes']} · expected generations: {p['generations']}",
             f"  estimated cost: {cost}"]
    lines += [f"  shot {r['shot']} · {r['step']} · {r['seconds']}s · model: {r['model'] or 'NOT CONFIGURED'} · "
              f"cost: {r['cost'] if r['cost'] is not None else 'unknown'}" for r in p["rows"]]
    lines += [f"  shot {n} · {kind} · made in the edit, no generation" for n, kind in p["not_generated"]]
    return "\n".join(lines)


def sheet(pkg: dict, out_dir: Path, cfg: dict) -> str:
    """generation_sheet.md: one block per generated shot, ready to paste into the Higgsfield app."""
    p = plan(pkg, cfg)
    lines = [f"# Generation sheet · {pkg['video_id']}", "",
             f"Format {pkg['format']['aspect']} · total {runtime(pkg):.0f}s · {p['generated_scenes']} scenes to generate "
             f"({p['generations']} generations) · generate each shot a little long and trim in the edit.", "",
             "Save each clip into `assets/` as `shot-<n>.mp4`, then run `python scripts/make_video.py ingest "
             f"{pkg['video_id']}`. Note the model and the credits spent beside each shot so cost per video can be recorded.", ""]
    for n, s in enumerate(pkg["shots"], 1):
        kind = asset_type(s)
        if not is_generated(s, cfg):
            lines += [f"## Shot {n} · {s['seconds']}s · {kind} (not generated)", "", f"{s['visual']}", ""]
            continue
        how = "text to video" if kind == "AI_VIDEO" else "generate a still, then animate it (image to video)"
        lines += [f"## Shot {n} · {s['seconds']}s · {s['shot_type']} · {how}", "", f"Camera: {s['camera']}", "",
                  "```", s["higgsfield_prompt"], "```", "", "- [ ] generated   model: ______   credits: ______", ""]
    path = out_dir / "generation_sheet.md"
    path.write_text("\n".join(lines))
    return f"Manual generation: sheet written to {path}. Nothing was sent to Higgsfield."


# ---------------------------------------------------------------- assets
def asset_for(out_dir: Path, shot: int) -> Path | None:
    return next((p for e in EXT if (p := out_dir / "assets" / f"shot-{shot}{e}").exists()), None)


def ingest(pkg: dict, out_dir: Path, cfg: dict) -> tuple[list[int], list[int]]:
    """(shots with an asset, shots still missing). When every generated shot has a file in assets/
    the package moves to READY_FOR_REVIEW. Works for clips made by hand or downloaded by the API."""
    need = [n for n, s in enumerate(pkg["shots"], 1) if is_generated(s, cfg)]
    have = [n for n in need if asset_for(out_dir, n)]
    missing = [n for n in need if n not in have]
    pkg.setdefault("render", {})["assets"] = {str(n): asset_for(out_dir, n).name for n in have}
    if not missing and pkg["status"] in ("READY_FOR_GENERATION", "GENERATING"):
        set_status(pkg, "READY_FOR_REVIEW", f"all {len(need)} generated shots are in assets/")
    elif have and pkg["status"] == "READY_FOR_GENERATION":
        set_status(pkg, "GENERATING", f"{len(have)}/{len(need)} shots in assets/")
    return have, missing


# ---------------------------------------------------------------- API adapter
class NotReady(Exception):
    """The API path cannot run yet; the message says exactly what is missing."""


def _session(cfg: dict):
    kid, secret = os.environ.get("HF_API_KEY_ID"), os.environ.get("HF_API_KEY_SECRET")
    if not (kid and secret):
        raise NotReady("HF_API_KEY_ID and HF_API_KEY_SECRET are not set in the environment (.env).")
    import requests
    s = requests.Session()
    s.headers.update({"Authorization": f"Key {kid}:{secret}", "Content-Type": "application/json"})
    return s


def _fill(template, values: dict):
    """Fill "{prompt}", "{seconds}", "{aspect}" and "{image_url}" in a params template. A value that
    is exactly one placeholder keeps its type, so "{seconds}" becomes a number."""
    if isinstance(template, dict):
        return {k: _fill(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, values) for v in template]
    if isinstance(template, str):
        for k, v in values.items():
            if template == "{" + k + "}":
                return v
            template = template.replace("{" + k + "}", str(v))
    return template


def _jobs(pkg: dict, shot: int, step: str) -> list[dict]:
    return [j for j in pkg["render"]["jobs"] if j["shot"] == shot and j["step"] == step]


def _next_step(pkg: dict, n: int, s: dict, out_dir: Path, cfg: dict) -> tuple[str | None, str]:
    """(step to submit now, why). Never returns a step that already has a live or completed job, so
    running submit twice cannot pay for the same shot twice."""
    if asset_for(out_dir, n):
        return None, "asset already in assets/"
    retries = _hf(cfg).get("max_retries", 1)
    for step in STEPS[asset_type(s)]:
        jobs = _jobs(pkg, n, step)
        if any(j["status"] == DONE for j in jobs):
            continue
        if any(j["status"] in LIVE for j in jobs):
            return None, f"{step} is still running"
        if any(j["status"] == "nsfw" for j in jobs):
            return None, f"{step} was rejected by content moderation: rewrite the prompt, it is never resubmitted as is"
        if len(jobs) > retries:
            return None, f"{step} failed {len(jobs)} times: not retried again automatically"
        return step, "retry after a failure" if jobs else "not submitted yet"
    return None, "generated; waiting for download (run poll)"


def submit(pkg: dict, out_dir: Path, cfg: dict, confirm: bool = False, save=None, session=None) -> str:
    """Submit every shot that needs a generation. Without confirm=True this only prints the plan."""
    hf = _hf(cfg)
    if hf["adapter"] != "api":
        return (plan_text(pkg, cfg) + "\n\nAdapter is 'manual' (config/publishing.yaml -> video.higgsfield.adapter).\n"
                + sheet(pkg, out_dir, cfg))
    todo = []
    for n, s in enumerate(pkg["shots"], 1):
        if is_generated(s, cfg):
            step, why = _next_step(pkg, n, s, out_dir, cfg)
            if step:
                todo.append((n, s, step, why))
    missing = sorted({step for _, _, step, _ in todo if not (hf["models"].get(step) or {}).get("path")})
    if missing:
        raise NotReady(f"No model path configured for: {', '.join(missing)} (config/publishing.yaml -> video.higgsfield.models).")
    text = plan_text(pkg, cfg) + f"\n\nTo submit now: {len(todo)} generation(s): " + \
        (", ".join(f"shot {n} {step} ({why})" for n, _, step, why in todo) or "none")
    if not todo:
        return text
    if not confirm:
        return text + "\n\nNothing was submitted. This spends Higgsfield credits: run again with --confirm to go ahead."
    session = session or _session(cfg)
    for n, s, step, _ in todo:
        m = hf["models"][step]
        image = next((j.get("output_url") for j in _jobs(pkg, n, "text_to_image") if j["status"] == DONE), None)
        body = _fill(m.get("params") or {}, {"prompt": s["higgsfield_prompt"], "seconds": s["seconds"],
                                             "aspect": pkg["format"]["aspect"], "image_url": image})
        r = session.post(hf["base_url"].rstrip("/") + "/" + m["path"].lstrip("/"), data=json.dumps(body), timeout=60)
        r.raise_for_status()
        data = r.json()
        pkg["render"]["jobs"].append({"shot": n, "step": step, "model": m.get("name") or m["path"],
                                      "request_id": data["request_id"], "status_url": data["status_url"],
                                      "status": data.get("status", "queued"), "cost": m.get("cost_per_generation"),
                                      "submitted_at": iso(now_utc()), "output_url": None, "error": None})
        set_status(pkg, "GENERATING", f"submitted shot {n} {step}")
        if save:
            save(pkg)          # the job id is on disk before the next paid request goes out
    _record_cost(pkg)
    return text + f"\n\nSubmitted {len(todo)} generation(s). Job ids are saved. Run `poll` to collect the results."


def _record_cost(pkg: dict) -> None:
    costs = [j["cost"] for j in pkg["render"]["jobs"]]
    pkg["render"]["cost"] = None if any(c is None for c in costs) else round(sum(costs), 2)
    pkg["render"]["generations"] = len(costs)


def poll(pkg: dict, out_dir: Path, cfg: dict, save=None, session=None) -> str:
    """Check every unfinished job once, download finished outputs into assets/, update the status."""
    live = [j for j in pkg["render"]["jobs"] if j["status"] in LIVE or (j["status"] == DONE and not j.get("output_url"))]
    if not live:
        have, missing = ingest(pkg, out_dir, cfg)
        return f"No jobs in progress. Assets: {len(have)} present, missing shots {missing or 'none'}. Status {pkg['status']}."
    session = session or _session(cfg)
    (out_dir / "assets").mkdir(exist_ok=True)
    lines = []
    for j in live:
        r = session.get(j["status_url"], timeout=60)
        r.raise_for_status()
        data = r.json()
        j["status"] = data.get("status", j["status"])
        if j["status"] == DONE:
            url = (data.get("video") or {}).get("url") or next((i.get("url") for i in data.get("images") or []), None)
            j["output_url"] = url
            if url and j["step"] != "text_to_image":
                ext = Path(url.split("?")[0]).suffix or ".mp4"
                (out_dir / "assets" / f"shot-{j['shot']}{ext}").write_bytes(session.get(url, timeout=300).content)
        elif j["status"] not in LIVE:
            j["error"] = data.get("error") or j["status"]
        lines.append(f"shot {j['shot']} {j['step']}: {j['status']}" + (f" ({j['error']})" if j.get("error") else ""))
        if save:
            save(pkg)
    have, missing = ingest(pkg, out_dir, cfg)
    stills = [j for j in pkg["render"]["jobs"] if j["step"] == "text_to_image" and j["status"] == DONE
              and not _jobs(pkg, j["shot"], "image_to_video")]
    lines.append(f"Assets: {len(have)} present, missing shots {missing or 'none'}. Status {pkg['status']}.")
    if stills:
        lines.append(f"{len(stills)} still(s) are ready to animate: run `render --confirm` again to submit the motion step.")
    if any(j["status"] in ("failed", "nsfw", "canceled") for j in pkg["render"]["jobs"]) and missing:
        lines.append("Some shots failed. `render` shows which can be retried; a moderated shot needs a new prompt first.")
    return "\n".join(lines)
