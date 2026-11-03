"""PRODUCE: turn a checked video package into a finished 9:16 MP4.

  narration (Higgsfield text-to-speech, one clip per voiceover line)
  -> timeline (every shot lasts as long as the lines spoken over it)
  -> assets (Higgsfield stills and clips, with one reference image for continuity)
  -> graphics (the Leonida Desk visual system: research/design.py, config/design.yaml)
  -> assembly (FFmpeg: scenes, overlays, captions, voice, clip sound, music, loudness)

Generation goes through the installed `higgsfield` CLI, which is already authenticated; nothing
here holds a credential. Every job id is written to the package before the job is waited on, and
a step whose output file already exists is skipped, so a run that is interrupted can simply be
started again without paying twice. Editing is deterministic and local: Higgsfield makes pictures
and sound, FFmpeg cuts them.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import design
from .articles import iso, now_utc
from .video import asset_type, is_generated, set_status

W, H, FPS = 1080, 1920, 30


_LOCK = threading.Lock()      # jobs run in parallel; the package file is written by one at a time


class ProduceError(Exception):
    pass


def _cfg(cfg: dict) -> dict:
    return cfg["publishing"]["video"]["production"]


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ff(*args: str) -> None:
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        raise ProduceError(f"ffmpeg failed: {r.stderr.strip()[-600:]}")


def probe(path: Path) -> tuple[float, bool]:
    """(duration in seconds, has an audio stream)."""
    err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        raise ProduceError(f"cannot read {path.name}")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), "Audio:" in err


# ---------------------------------------------------------------- Higgsfield CLI
def hf(*args: str, timeout: int = 1800) -> list | dict:
    r = subprocess.run(["higgsfield", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise ProduceError(f"higgsfield {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[-400:]}")
    return json.loads(r.stdout)


def estimate(model: str, params: list[str]) -> float | None:
    r = subprocess.run(["higgsfield", "generate", "cost", model, *params], capture_output=True, text=True)
    m = re.search(r"([\d.]+)\s+credits", r.stdout)
    return float(m[1]) if m else None


def generate(pkg: dict, key: str, model: str, params: list[str], out: Path, save, media: list[str] = ()) -> Path:
    """Run one Higgsfield job and download its result to `out`. Skips when `out` already exists;
    rejoins a job that was submitted on an earlier run; retries one plain failure."""
    if out.exists():
        return out
    jobs = pkg["render"].setdefault("jobs", [])
    unlocked, save = save, None

    def save(p):
        with _LOCK:
            unlocked(p)
    retries = 1
    while True:
        job = next((j for j in jobs if j["key"] == key and j["status"] in ("submitted", "completed")), None)
        if job is None:
            cost = estimate(model, params)             # media inputs do not change the price estimate
            made = hf("generate", "create", model, *params, *media)
            jid = _job_id(made)
            job = {"key": key, "job_id": jid, "model": model, "status": "submitted", "credits": cost,
                   "submitted_at": iso(now_utc()), "url": None}
            jobs.append(job)
            save(pkg)                                  # the job id is on disk before we wait on it
        res = hf("generate", "wait", job["job_id"], "--timeout", "30m", "--quiet")
        res = res[0] if isinstance(res, list) else res
        job["status"], job["url"] = res.get("status"), res.get("result_url")
        save(pkg)
        if job["status"] == "completed" and job["url"]:
            break
        if job["status"] == "nsfw":
            raise ProduceError(f"{key}: rejected by content moderation. Rewrite the prompt; it is not resubmitted as is.")
        if retries == 0:
            raise ProduceError(f"{key}: generation ended as {job['status']}")
        retries -= 1
    ext = Path(job["url"].split("?")[0]).suffix or out.suffix
    out = out.with_suffix(ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(job["url"], out)
    job["asset"] = out.name
    save(pkg)
    return out


def _job_id(made) -> str:
    """The id from `generate create --json`, whichever shape the CLI returns."""
    if isinstance(made, dict):
        made = made.get("id") or made.get("job_id") or made.get("ids") or made.get("job_ids") or made.get("jobs") or made.get("items")
    first = made[0] if isinstance(made, list) else made
    return first if isinstance(first, str) else first["id"]


_WHISPER = None


def spoken_words(path: Path) -> str:
    """Any speech a local recogniser hears in an audio or video file ("" if none, or if the
    recogniser is not installed). Generated sound sometimes contains a voice, and an audio model
    can read its own prompt aloud; nobody is listening during a run, so the pipeline checks."""
    global _WHISPER
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        return ""
    raw = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    if len(audio) < 8000:
        return ""
    with _LOCK:
        if _WHISPER is None:
            _WHISPER = WhisperModel("base.en", device="cpu", compute_type="int8")
        # In pieces: on a long file the recogniser can stop early and report less than was said
        step, parts = 16000 * 20, []
        for a in range(0, len(audio), step):
            piece = audio[a:a + step]
            if len(piece) >= 8000:
                parts += [s.text.strip() for s in _WHISPER.transcribe(piece, vad_filter=True)[0] if s.no_speech_prob < 0.3]
    text = " ".join(parts)
    return text if len(text.split()) >= 2 else ""


def sound(pkg: dict, key: str, prompt: str, seconds: float, d: Path, cfg: dict, save, model: str) -> Path | None:
    """One generated sound (an effect or a bed), refused if a voice is heard in it. Tried twice,
    then left out: a missing effect is better than a second narrator."""
    assets = d / "assets"
    params = ["--prompt", prompt] + (["--duration", str(max(1, math.ceil(seconds)))] if model in _cfg(cfg)["duration_models"] else [])
    for _ in range(2):
        f = find(assets, key) or generate(pkg, key, model, params, assets / f"{key}.wav", save)
        heard = spoken_words(f)
        if not heard:
            return f
        (assets / "rejected").mkdir(exist_ok=True)
        f.rename(assets / "rejected" / f"{key}-spoken-{now_utc():%H%M%S}{f.suffix}")
        for j in pkg["render"]["jobs"]:
            if j["key"] == key and j["status"] == "completed":
                j["status"], j["note"] = "rejected", f"a voice was heard in it: {heard[:80]}"
        save(pkg)
    pkg["render"].setdefault("dropped_sounds", []).append(key)
    return None


def find(d: Path, stem: str) -> Path | None:
    return next(iter(sorted(d.glob(stem + ".*"))), None)


# ---------------------------------------------------------------- plan
def speak(text: str) -> str:
    """What the voice is asked to say: no quote marks, which engines tend to read oddly."""
    return re.sub(r'["“”]', "", text).strip()


def plan(pkg: dict, cfg: dict) -> dict:
    """Every generation the package needs, with an estimated credit cost from the CLI itself."""
    c = _cfg(cfg)
    rows = []
    tts = ["--variant", c["voice"]["variant"], "--voice_id", c["voice"]["id"], "--voice_type", c["voice"]["type"]]
    for n, line in enumerate(pkg["voiceover"], 1):
        rows.append((f"vo-{n}", c["voice"]["model"], ["--prompt", speak(line["text"]), *tts]))
    if (pkg.get("continuity") or {}).get("reference_prompt"):
        rows.append(("reference", c["image_model"], ["--prompt", "x", "--aspect_ratio", "9:16"]))
    for n, s in enumerate(pkg["shots"], 1):
        if not is_generated(s, cfg):
            continue
        if asset_type(s) == "AI_IMAGE_WITH_MOTION":
            rows.append((f"still-{n}", c["image_model"], ["--prompt", "x", "--aspect_ratio", "9:16"]))
        secs = max(c["min_clip_seconds"], math.ceil(s["seconds"] + 0.5))
        rows.append((f"shot-{n}", c["video_model"], ["--prompt", "x", "--duration", str(secs), "--resolution", c["resolution"],
                                                     "--aspect_ratio", "9:16"]))
    if c.get("music", {}).get("enabled") and pkg.get("music_prompt"):
        rows.append(("music", c["music"]["model"], ["--prompt", "x", "--duration", "45"]))
    dur = lambda model, secs: ["--duration", str(max(1, math.ceil(secs)))] if model in c["duration_models"] else []
    for n, _ in enumerate(pkg.get("audio_beds") or [], 1):
        rows.append((f"bed-{n}", c["bed_model"], ["--prompt", "x", *dur(c["bed_model"], 20)]))
    for n, s in enumerate(pkg["shots"], 1):
        for k, fx in enumerate(s.get("sfx") or [], 1):
            rows.append((f"sfx-{n}-{k}", c["sfx_model"], ["--prompt", "x", *dur(c["sfx_model"], fx.get("seconds", 3))]))
    with ThreadPoolExecutor(8) as ex:
        costs = list(ex.map(lambda r: estimate(r[1], r[2]), rows))
    return {"rows": [{"key": k, "model": m, "credits": cost} for (k, m, _), cost in zip(rows, costs)],
            "total": None if any(x is None for x in costs) else round(sum(costs), 1)}


def plan_text(pkg: dict, cfg: dict) -> str:
    p = plan(pkg, cfg)
    by: dict[str, list] = {}
    for r in p["rows"]:
        by.setdefault(r["model"], []).append(r)
    lines = [f"Production plan · {pkg['video_id']}",
             f"  scenes: {len(pkg['shots'])} · generations: {len(p['rows'])} · estimated cost: "
             + (f"{p['total']} credits" if p["total"] is not None else "unknown") + " (estimates from `higgsfield generate cost`)"]
    for model, rows in by.items():
        cost = sum(r["credits"] or 0 for r in rows)
        lines.append(f"  {model}: {len(rows)} job(s), about {cost:.1f} credits · " + ", ".join(r["key"] for r in rows))
    lines.append("  graphics, captions, timing and the edit are made locally: no credits")
    return "\n".join(lines)


# ---------------------------------------------------------------- timeline
def timeline(pkg: dict, vo: dict[int, float], cfg: dict) -> dict:
    """Shot lengths from the narration: a shot lasts as long as the lines spoken over it."""
    c = _cfg(cfg)
    gap, lead = c["line_gap_seconds"], c["lead_in_seconds"]
    shots, t = [], 0.0
    for n, s in enumerate(pkg["shots"], 1):
        lines = [ln for ln in s.get("vo_lines", []) if ln in vo]
        dur = sum(vo[ln] + gap for ln in lines) if lines else float(s["seconds"])
        dur += lead if n == 1 else 0
        dur += c["tail_seconds"] if n == len(pkg["shots"]) else 0
        dur = round(max(dur, c["min_shot_seconds"]), 2)
        cues, lt = [], t + (lead if n == 1 else 0)
        for ln in lines:
            cues.append({"line": ln, "start": round(lt, 3), "end": round(lt + vo[ln], 3)})
            lt += vo[ln] + gap
        shots.append({"shot": n, "start": round(t, 3), "duration": dur, "lines": cues})
        t += dur
    return {"total": round(t, 2), "shots": shots}


# ---------------------------------------------------------------- the run
def produce(pkg: dict, d: Path, cfg: dict, save, log=print, output: str = "final.mp4") -> Path:
    c = _cfg(cfg)
    assets, work = d / "assets", d / "assets" / "work"
    work.mkdir(parents=True, exist_ok=True)
    pkg.setdefault("render", {}).update({"adapter": "higgsfield-cli"})
    set_status(pkg, "GENERATING", "production run started")
    save(pkg)
    nshots = len(pkg["shots"])

    # 1. narration: one clip per line, so every line's length is known exactly
    log("NARRATION")
    tts = ["--variant", c["voice"]["variant"], "--voice_id", c["voice"]["id"], "--voice_type", c["voice"]["type"]]

    def say(item):
        n, line = item
        return n, generate(pkg, f"vo-{n}", c["voice"]["model"], ["--prompt", speak(line["text"]), *tts], assets / f"vo-{n}.mp3", save)
    with ThreadPoolExecutor(4) as ex:
        vo_files = dict(ex.map(say, enumerate(pkg["voiceover"], 1)))
    vo = {}
    for n, f in vo_files.items():       # trim the silence engines leave at each end
        clean = work / f"vo-{n}.wav"
        ff("-i", str(f), "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,areverse,"
           "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse", "-ar", "48000", "-ac", "2", str(clean))
        vo[n] = probe(clean)[0]

    # 2. timing from the voice
    tl = timeline(pkg, vo, cfg)
    lo, hi = cfg["publishing"]["video"]["seconds"]
    log(f"TIMELINE {tl['total']}s · " + " ".join(f"{s['shot']}:{s['duration']}" for s in tl["shots"]))
    if not lo <= tl["total"] <= hi + c["overrun_tolerance_seconds"]:
        raise ProduceError(f"the narration makes a {tl['total']}s video; a short must be {lo}-{hi}s. Tighten the script.")
    (d / "timeline.json").write_text(json.dumps(tl, indent=2) + "\n")

    # 3. pictures: one reference image carries the hero subject and setting across shots
    log("ASSETS")
    cont = pkg.get("continuity") or {}
    ref = None
    if cont.get("reference_prompt"):
        ref = generate(pkg, "reference", c["image_model"], ["--prompt", cont["reference_prompt"], "--aspect_ratio", "9:16"],
                       assets / "reference.png", save)

    def shoot(n: int) -> None:
        s = pkg["shots"][n - 1]
        dur = tl["shots"][n - 1]["duration"]
        secs = str(max(c["min_clip_seconds"], math.ceil(dur + 0.3)))
        prompt = s["higgsfield_prompt"] + " " + c["clip_audio_prompt"]
        params = ["--prompt", prompt, "--duration", secs, "--resolution", c["resolution"], "--aspect_ratio", "9:16"]
        media = []
        if asset_type(s) == "AI_IMAGE_WITH_MOTION":
            still = generate(pkg, f"still-{n}", c["image_model"], ["--prompt", s["higgsfield_prompt"], "--aspect_ratio", "9:16"],
                             assets / f"still-{n}.png", save)
            params += ["--mode", "omni_reference"] if c["video_model"] in c.get("reference_mode_models", []) else []
            media = ["--start-image", str(still)]
        elif ref and s.get("reference"):
            params += ["--mode", "omni_reference"] if c["video_model"] in c.get("reference_mode_models", []) else []
            media = ["--image", str(ref)]
        if not find(assets, f"shot-{n}"):
            generate(pkg, f"shot-{n}", c["video_model"], params, assets / f"shot-{n}.mp4", save, media)
    gen = [n for n, s in enumerate(pkg["shots"], 1) if is_generated(s, cfg)]
    with ThreadPoolExecutor(c["parallel_jobs"]) as ex:
        list(ex.map(shoot, gen))

    # 4. sound beds
    music = None
    if c.get("music", {}).get("enabled") and pkg.get("music_prompt"):
        music = find(assets, "music") or generate(pkg, "music", c["music"]["model"],
                                                  ["--prompt", pkg["music_prompt"], "--duration", str(math.ceil(tl["total"]) + 1)],
                                                  assets / "music.mp3", save)
    beds = []
    for n, bed in enumerate(pkg.get("audio_beds") or [], 1):
        f = sound(pkg, f"bed-{n}", bed["prompt"], 20, d, cfg, save, c["bed_model"])
        if f:
            beds.append((bed, f))
    # sound events: what happens on screen is heard (a slide, an impact, a thunderclap, a riser)
    hits = []
    for n, s in enumerate(pkg["shots"], 1):
        for k, fx in enumerate(s.get("sfx") or [], 1):
            f = sound(pkg, f"sfx-{n}-{k}", fx["prompt"], fx.get("seconds", 3.0), d, cfg, save, c["sfx_model"])
            if f:
                hits.append((n, fx, f))

    # 5. footage: one clean segment per shot, no text. A shot with no clip of its own runs over
    #    footage we already have (the rest of an earlier clip, another take, or a still), with a
    #    slow push so a held frame never sits dead. No full-screen cards.
    log("FOOTAGE")
    push = cfg["design"]["motion"]["hold_push"]
    used: dict[str, float] = {}
    segs = []
    for n, s in enumerate(pkg["shots"], 1):
        dur = tl["shots"][n - 1]["duration"]
        seg = work / f"seg-{n}.mp4"
        own = {"shot": n, **({"start": s["clip_start"]} if "clip_start" in s else {}), **({"speed": s["clip_speed"]} if "clip_speed" in s else {})}
        spec = own if is_generated(s, cfg) else (s.get("footage") or ({"shot": s["reuse_shot"]} if s.get("reuse_shot") else {}))
        src = find(assets, f"shot-{spec['shot']}") if spec.get("shot") else (assets / spec["asset"] if spec.get("asset") else None)
        hold = not is_generated(s, cfg)
        zoom = (f",scale={W * 2}:{H * 2},zoompan=z='1+{push}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}"
                if hold else "")
        enc = ["-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-an", "-t", f"{dur}", str(seg)]
        fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        if src is None or not src.exists():
            ff("-f", "lavfi", "-i", f"color=c=0x101014:s={W}x{H}:r={FPS}", *enc)
        elif src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            ff("-loop", "1", "-framerate", str(FPS), "-i", str(src), "-vf", f"{fit}{zoom or ''},format=yuv420p", *enc)
        else:
            key = str(src)
            off = spec.get("start", used.get(key, 0.0) if hold else 0.0)
            speed = spec.get("speed", 1.0)
            ff("-ss", f"{off}", "-i", str(src), "-vf",
               f"setpts={1 / speed}*PTS,{fit},fps={FPS},tpad=stop_mode=clone:stop_duration=15{zoom}", *enc)
            used[key] = off + dur * speed
        segs.append(seg)
    (work / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in segs))
    body = work / "body.mp4"
    ff("-f", "concat", "-safe", "0", "-i", str(work / "concat.txt"), "-c", "copy", str(body))

    # 6. the graphic layer, composited frame by frame over the footage
    log("GRAPHICS")
    elements, caps = design.layers(pkg, tl, cfg)
    silent = work / "video.mp4"
    proc = subprocess.Popen([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(body),
                             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[o]", "-map", "[o]",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-an", str(silent)],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in design.frames(elements, cfg, tl["total"]):
            proc.stdin.write(frame)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait():
        raise ProduceError(f"ffmpeg failed on the graphic layer: {proc.stderr.read().decode()[-500:]}")
    (d / "captions.srt").write_text("".join(
        f"{n}\n{_srt(cap['start'])} --> {_srt(cap['end'])}\n{cap['text']}\n\n" for n, cap in enumerate(caps, 1)))

    # 7. sound: voice on top, each clip's own sound and the beds underneath
    log("SOUND")
    ain, parts = [], []

    def add(path: Path, filt: str, loop: bool = False) -> None:
        ain.extend((["-stream_loop", "-1"] if loop else []) + ["-i", str(path)])
        parts.append(f"[{len(parts)}:a]aformat=sample_rates=48000:channel_layouts=stereo,{filt}[a{len(parts)}]")
    for s in tl["shots"]:
        for cue in s["lines"]:
            add(work / f"vo-{cue['line']}.wav", f"volume={c['mix']['voice_db']}dB,adelay={int(cue['start'] * 1000)}:all=1")
        clip = find(assets, f"shot-{s['shot']}") if is_generated(pkg["shots"][s["shot"] - 1], cfg) else None
        if clip and probe(clip)[1] and "clip_start" not in pkg["shots"][s["shot"] - 1]:
            heard = spoken_words(clip)
            if heard:                      # a generated clip with a voice in it keeps its picture and loses its sound
                pkg["render"].setdefault("muted_clips", []).append({"shot": s["shot"], "heard": heard[:80]})
                continue
            dur = s["duration"]
            add(clip, f"atrim=0:{dur},afade=t=in:d=0.12,afade=t=out:st={max(0, dur - 0.25)}:d=0.25,"
                      f"volume={c['mix']['clip_db']}dB,adelay={int(s['start'] * 1000)}:all=1")
    for bed, f in beds:
        a = tl["shots"][bed.get("from_shot", 1) - 1]["start"]
        last_s = tl["shots"][bed.get("to_shot", nshots) - 1]
        length = last_s["start"] + last_s["duration"] - a
        add(f, f"atrim=0:{length},afade=t=in:d=0.6,afade=t=out:st={max(0, length - 1.2)}:d=1.2,"
               f"volume={bed.get('db', c['mix']['bed_db'])}dB,adelay={int(a * 1000)}:all=1", loop=True)
    for n, fx, f in hits:
        at = tl["shots"][n - 1]["start"] + fx.get("at", 0.0)
        length = fx.get("seconds", 3.0)
        add(f, f"atrim=0:{length},afade=t=in:d=0.03,afade=t=out:st={max(0, length - 0.4)}:d=0.4,"
               f"volume={min(fx.get('db', c['mix']['sfx_db']), -4)}dB,adelay={int(at * 1000)}:all=1")
    if music:
        add(music, f"atrim=0:{tl['total']},afade=t=in:d=0.4,afade=t=out:st={max(0, tl['total'] - 1.5)}:d=1.5,volume={c['mix']['music_db']}dB",
            loop=True)
    mix = work / "mix.wav"
    ff(*ain, "-filter_complex", ";".join(parts) + ";" + "".join(f"[a{n}]" for n in range(len(parts)))
       + f"amix=inputs={len(parts)}:normalize=0:duration=longest,loudnorm=I=-14:TP=-1.5:LRA=11,apad[m]",
       "-map", "[m]", "-t", f"{tl['total']}", "-ar", "48000", str(mix))

    final = d / output
    ff("-i", str(silent), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
       "-movflags", "+faststart", "-t", f"{tl['total']}", str(final))
    # the last check nobody else can do during a run: is the narrator the only voice in the mix?
    heard = spoken_words(final)
    if heard:
        norm = lambda t: re.sub(r"[^a-z0-9 ]", "", t.lower().replace("-", " ")).split()
        script, mix = norm(" ".join(speak(v["text"]) for v in pkg["voiceover"])), norm(heard)
        extra, missing = max(0, len(mix) - len(script)), max(0, len(script) - len(mix))
        slack = max(3, len(script) // 10)      # numbers and contractions are heard as different word counts
        pkg["render"]["audio_check"] = {"heard": heard, "script_words": len(script), "heard_words": len(mix),
                                        "extra_words": extra, "missing_words": missing, "ok": extra <= slack and missing <= slack}
        log(f"AUDIO CHECK script {len(script)} words · heard {len(mix)} · " + ("ok" if pkg["render"]["audio_check"]["ok"] else "CHECK THE MIX: extra or missing speech"))
    credits = [j.get("credits") for j in pkg["render"]["jobs"]]
    versions = [v for v in pkg["render"].get("versions", []) if v != final.name] + [final.name]
    pkg["render"].update({"versions": versions, "design": "config/design.yaml",
                          "final": final.name, "seconds": tl["total"], "timeline": "timeline.json", "captions": "captions.srt",
                          "voice": c["voice"]["name"], "models": sorted({j["model"] for j in pkg["render"]["jobs"]}),
                          "generations": len(credits), "produced_at": iso(now_utc()),
                          "cost": None if any(x is None for x in credits) else round(sum(credits), 2), "cost_unit": "credits (estimated)"})
    set_status(pkg, "READY_FOR_REVIEW", f"final.mp4 assembled, {tl['total']}s")
    save(pkg)
    return final


def _srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
