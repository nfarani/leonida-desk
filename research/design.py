"""LEONIDA DESK VISUAL SYSTEM: the graphic layer of every video.

Everything on screen that is not footage is drawn here from config/design.yaml: the brand bug, the
opening hook, captions with highlighted words, editorial tags, source lines, the brief AI label and
the end card. Elements are small transparent images with a start, an end and a short fade; the
compositor lays the active ones over the footage frame by frame. Nothing here generates anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import resolve


@dataclass
class Element:
    name: str
    img: object               # PIL RGBA image, cropped to its content
    x: int
    y: int
    start: float
    end: float
    fade_in: float
    fade_out: float
    rise: int = 0


def _d(cfg: dict) -> dict:
    return cfg["design"]


def rgba(hexcolor: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    h = hexcolor.lstrip("#")
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(a * opacity)


def font(cfg: dict, role: str, size: int):
    from PIL import ImageFont
    spec = _d(cfg)["fonts"][role]
    f = ImageFont.truetype(str(resolve(cfg, _d(cfg)["fonts"]["dir"]) / spec["file"]), size)
    if "weight" in spec:
        axes = f.get_variation_axes()
        f.set_variation_by_axes([spec["weight"] if a["name"] == b"Weight" else min(a["maximum"], max(a["minimum"], size))
                                 for a in axes])
    return f


def _width(run_font, text: str, tracking: int = 0) -> float:
    return run_font.getlength(text) + tracking * max(0, len(text) - 1)


def text_image(cfg: dict, lines: list[list[tuple]], line_height: int, align: str = "left", tracking: int = 0,
               opacity: float = 1.0, pad: int = 24):
    """Lines of (text, font, colour) runs on a transparent image with one soft shadow. No boxes, no outlines."""
    from PIL import Image, ImageDraw, ImageFilter
    sh = _d(cfg)["shadow"]
    widths = [sum(_width(f, t, tracking) for t, f, _ in line) for line in lines]
    w, h = int(max(widths)) + 2 * pad, line_height * len(lines) + 2 * pad
    ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ink)
    for n, line in enumerate(lines):
        x = pad + {"left": 0, "center": (max(widths) - widths[n]) / 2, "right": max(widths) - widths[n]}[align]
        size = max(f.size for _, f, _ in line)
        for text, f, fill in line:
            y = pad + n * line_height + (line_height - size) / 2 + (size - f.size) * 0.78   # shared baseline
            if tracking:
                for ch in text:
                    d.text((x, y), ch, font=f, fill=fill)
                    x += f.getlength(ch) + tracking
                x -= tracking
            else:
                d.text((x, y), text, font=f, fill=fill)
                x += f.getlength(text)
    # two shadows, no outline: a wide soft one for bright footage and a tight one that keeps edges crisp
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for blur, strength in ((sh["blur"], sh["opacity"]), (sh["tight_blur"], sh["tight_opacity"])):
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shadow.paste(rgba(_d(cfg)["colors"]["shadow"], strength), (0, sh["offset"]), ink.getchannel("A"))
        out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(blur)))
    out = Image.alpha_composite(out, ink)
    if opacity < 1:
        out.putalpha(out.getchannel("A").point(lambda v: int(v * opacity)))
    return out


def with_bar(cfg: dict, img, color: str, width: int, gap: int, top: int = 0, bottom: int = 0):
    """A thin accent bar to the left of a text image: the system's only non-text mark."""
    from PIL import Image, ImageDraw
    out = Image.new("RGBA", (img.width + width + gap, img.height), (0, 0, 0, 0))
    out.alpha_composite(img, (width + gap, 0))
    ImageDraw.Draw(out).rounded_rectangle([0, 24 + top, width, img.height - 24 - bottom], width // 2, fill=rgba(color))
    return out


def marked(cfg: dict, text: str, f, accent_font=None) -> list[tuple]:
    """Runs from a line with *accented* words: "GTA VI *HURRICANES*"."""
    c = _d(cfg)["colors"]
    return [(part, accent_font or f, rgba(c["accent"]) if n % 2 else rgba(c["text"]))
            for n, part in enumerate(text.split("*")) if part]


def fitted(cfg: dict, lines: list[str], role: str, size: int, max_width: int):
    while size > 40 and max(font(cfg, role, size).getlength(ln.replace("*", "")) for ln in lines) > max_width:
        size -= 2
    return font(cfg, role, size)


# ---------------------------------------------------------------- the elements
def brand_bug(cfg: dict):
    b, c = _d(cfg)["brand_bug"], _d(cfg)["colors"]
    img = text_image(cfg, [[(b["text"][0], font(cfg, "headline", b["size"]), rgba(c["text"])), (" ", font(cfg, "label", b["size"]), (0, 0, 0, 0)),
                           (b["text"][1], font(cfg, "label", b["size"]), rgba(c["text_soft"]))]],
                     b["size"] + 6, tracking=b["tracking"], opacity=b["opacity"])
    return with_bar(cfg, img, c["accent"], b["mark"]["width"], b["mark"]["gap"], top=2, bottom=2)


def state_of(cfg: dict, name: str | None) -> str | None:
    if not name:
        return None
    c = _d(cfg)["colors"]
    name = name.strip().upper().rstrip("?")
    name = c["aliases"].get(name, name)
    return name if name in c["states"] else None


def tag(cfg: dict, state: str, text: str | None = None):
    """A compact corner tag. `text` replaces the state's name: a sourced fact shows its source
    ("GAME INFORMER") instead of a label about itself."""
    t, c = _d(cfg)["tag"], _d(cfg)["colors"]
    label = (text or state).upper() + ("?" if state == "WHAT IF" and not text else "")
    lines = [[(label, font(cfg, "label", t["size"]), rgba(c["text"]))]]
    img = text_image(cfg, lines, t["size"] + 8, tracking=t["tracking"])
    img = with_bar(cfg, img, c["states"][state], t["bar"]["width"], t["bar"]["gap"], top=2, bottom=2)
    if state in t["speculative_states"]:
        from PIL import Image
        sub = text_image(cfg, [[(_d(cfg)["disclosure"]["label"], font(cfg, "body", t["sub_size"]), rgba(c["text_soft"]))]], t["sub_size"] + 6)
        out = Image.new("RGBA", (max(img.width, sub.width + t["bar"]["width"] + t["bar"]["gap"]), img.height + sub.height - 40), (0, 0, 0, 0))
        out.alpha_composite(img, (out.width - img.width, 0))
        out.alpha_composite(sub, (out.width - sub.width, img.height - 40))
        return out
    return img


def ai_label(cfg: dict):
    dd, c = _d(cfg)["disclosure"], _d(cfg)["colors"]
    return text_image(cfg, [[(dd["label"], font(cfg, "body", dd["size"]), rgba(c["text_soft"]))]], dd["size"] + 6)


def title(cfg: dict, lines: list[str], spec: dict):
    s = _d(cfg)["safe"]
    f = fitted(cfg, lines, "headline", spec["size"], _d(cfg)["canvas"]["width"] - s["left"] - s["right_lower"])
    return text_image(cfg, [marked(cfg, ln.upper(), f) for ln in lines], f.size + spec["line_gap"])


def source(cfg: dict, quote: str, by: str | None, state: str | None):
    s, c, safe = _d(cfg)["source"], _d(cfg)["colors"], _d(cfg)["safe"]
    width = _d(cfg)["canvas"]["width"] - safe["left"] - safe["right_lower"] - 40
    fq = font(cfg, "label", s["quote_size"])
    words, lines, cur = f"“{quote.strip('\"“”')}”".split(), [], ""
    for w in words:
        if cur and fq.getlength(f"{cur} {w}") > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    rows = [[(ln, fq, rgba(c["text"]))] for ln in lines[:2]]
    if by:
        rows.append([(by, font(cfg, "body", s["by_size"]), rgba(c["text_soft"]))])
    img = text_image(cfg, rows, s["quote_size"] + 10)
    return with_bar(cfg, img, c["states"].get(state, c["accent"]), s["bar"]["width"], s["bar"]["gap"], top=6, bottom=6)


def scrim(cfg: dict):
    """A bottom gradient used only under the hook and the end card, never over the whole frame."""
    from PIL import Image
    s, w = _d(cfg)["scrim"], _d(cfg)["canvas"]["width"]
    col = Image.new("L", (1, s["height"]))
    col.putdata([int(255 * s["opacity"] * (y / s["height"]) ** 1.6) for y in range(s["height"])])
    img = Image.new("RGBA", (w, s["height"]), (0, 0, 0, 255))
    img.putalpha(col.resize((w, s["height"])))
    return img


# ---------------------------------------------------------------- captions
_NORM = re.compile(r"[^a-z0-9']+")


def caption_chunks(pkg: dict, tl: dict, cfg: dict, skip: set = frozenset(), plain: bool = False) -> list[dict]:
    """Short phrase chunks with a few highlighted words, each timed by its share of its line.
    `skip` leaves out lines that carry a punch caption; `plain` is the transcript, with every line."""
    c = _d(cfg)["captions"]
    out = []
    for s in tl["shots"]:
        for cue in s["lines"]:
            if cue["line"] in skip and not plain:
                continue
            line = pkg["voiceover"][cue["line"] - 1]
            text = line["text"]
            for a, b in _d(cfg).get("caption_replacements", {}).items():
                text = text.replace(a, b)
            words = re.sub(r'["“”]', "", text).split()
            norm = [_NORM.sub("", w.lower()) for w in words]
            flags = [False] * len(words)
            for phrase in line.get("emphasis", []):
                p = [_NORM.sub("", w.lower()) for w in phrase.split()]
                for i in range(len(words) - len(p) + 1):
                    if norm[i:i + len(p)] == p:
                        flags[i:i + len(p)] = [True] * len(p)
            chunks, cur = [], []
            for i, w in enumerate(words):
                inside = flags[i] and flags[cur[-1]] if cur else False       # never split a highlighted phrase
                if cur and len(" ".join(words[j] for j in cur + [i])) > c["max_chars"] + (10 if inside else 0):
                    chunks.append(cur)
                    cur = []
                cur.append(i)
                size = len(" ".join(words[j] for j in cur))
                if (w[-1] in ".?!:" and size >= 10) or (w[-1] in ",;" and size >= 18):
                    chunks.append(cur)
                    cur = []
            if cur:
                chunks.append(cur)
            for k in range(len(chunks) - 1, 0, -1):          # no orphaned word on its own
                if len(" ".join(words[j] for j in chunks[k])) < 9 and \
                        len(" ".join(words[j] for j in chunks[k - 1] + chunks[k])) <= c["max_chars"] + 8:
                    chunks[k - 1] += chunks.pop(k)
            total, t = sum(len(" ".join(words[j] for j in ch)) for ch in chunks), cue["start"]
            for ch in chunks:
                d = (cue["end"] - cue["start"]) * len(" ".join(words[j] for j in ch)) / total
                hi = [j for j in ch if flags[j]][: c["max_highlights"]]
                out.append({"words": [(words[j], j in hi) for j in ch], "text": " ".join(words[j] for j in ch),
                            "start": round(t, 3), "end": round(t + d, 3)})
                t += d
    return out


def caption(cfg: dict, words: list[tuple[str, bool]]):
    c, col = _d(cfg)["captions"], _d(cfg)["colors"]
    plain, bold = font(cfg, "body", c["size"]), font(cfg, "body_bold", c["size"])
    space = plain.getlength(" ")
    runs = [((w.upper() if hot and c["uppercase_highlights"] else w), bold if hot else plain,
             rgba(col["accent"]) if hot else rgba(col["text"]), hot) for w, hot in words]
    widths = [f.getlength(t) for t, f, _, _ in runs]
    total = sum(widths) + space * (len(runs) - 1)
    split = len(runs)
    if total > c["one_line_width"] and len(runs) > 1 and c["max_lines"] > 1:
        # two balanced lines; a break inside a highlighted phrase is the last resort
        def cost(k):
            a = sum(widths[:k]) + space * (k - 1)
            b = sum(widths[k:]) + space * (len(runs) - k - 1)
            return abs(a - b) + (10000 if max(a, b) > c["max_width"] else 0) + (400 if runs[k - 1][3] and runs[k][3] else 0)
        split = min(range(1, len(runs)), key=cost)
    lines = []
    for part in (runs[:split], runs[split:]):
        if part:
            line = []
            for t, f, fill, _ in part:
                line += ([(" ", plain, (0, 0, 0, 0))] if line else []) + [(t, f, fill)]
            lines.append(line)
    return text_image(cfg, lines, c["line_height"], align="center")


# ---------------------------------------------------------------- the layer list
def shot_graphics(pkg: dict, n: int) -> dict:
    """A shot's `graphics` block, or one read from its on_screen_text for packages written before it."""
    s = pkg["shots"][n - 1]
    if "graphics" in s:
        return s["graphics"] or {}
    first = re.split(r"\s+[|·]\s+", s.get("on_screen_text") or "")[0]
    m = re.match(r"(ON RECORD|NOT SAID|NOT CONFIRMED|WHAT IF)", first.upper())
    return {"tag": m[1]} if m else {}


def layers(pkg: dict, tl: dict, cfg: dict) -> tuple[list[Element], list[dict]]:
    """Every graphic element with its place and time, and the caption list (for the .srt)."""
    d, m = _d(cfg), _d(cfg)["motion"]
    W, safe, total = d["canvas"]["width"], d["safe"], tl["total"]
    fi, fo, rise = m["fade_in"], m["fade_out"], m["rise"]
    els: list[Element] = []

    bug = brand_bug(cfg)
    els.append(Element("brand", bug, safe["left"], safe["top"] - 24, 0, total, 0, 0))

    # hook: prominent, brief, then out of the way
    # (a video that opens on its money shot with a punch caption has no title: hook_title is optional)
    hook_lines = pkg.get("hook_title")
    hook_end = min(d["hook"]["seconds"], tl["shots"][0]["duration"]) if hook_lines else 0.0
    sc = scrim(cfg)
    if hook_lines:
        if d["hook"]["scrim"]:
            els.append(Element("scrim", sc, 0, d["canvas"]["height"] - sc.height, 0, hook_end, 0, m["hook_fade_out"]))
        h = title(cfg, hook_lines, d["hook"])
        els.append(Element("hook", h, safe["left"] - 24, d["hook"]["bottom"] - h.height + 24, 0.05, hook_end, fi, m["hook_fade_out"], rise))

    # the AI label: small, at the start
    a0, a1 = d["disclosure"]["seconds"] if d["disclosure"].get("on_screen") else (0.0, 0.0)
    if d["disclosure"].get("on_screen"):
        lab = ai_label(cfg)
        els.append(Element("ai", lab, W - safe["right"] - lab.width + 24, safe["top"] - 22, a0, a1, fi, 0.3))

    # editorial tags: one continuous tag across neighbouring shots in the same state
    states = [state_of(cfg, shot_graphics(pkg, s["shot"]).get("tag")) for s in tl["shots"]]
    texts = [shot_graphics(pkg, s["shot"]).get("tag_text") for s in tl["shots"]]
    i = 0
    while i < len(states):
        j = i
        while j + 1 < len(states) and (states[j + 1], texts[j + 1]) == (states[i], texts[i]):
            j += 1
        if states[i]:
            img = tag(cfg, states[i], texts[i])
            start = max(tl["shots"][i]["start"] + 0.1, a1 + 0.1 if tl["shots"][i]["start"] < a1 else 0)
            els.append(Element(f"tag:{states[i]}", img, W - safe["right"] - img.width + 24, safe["top"] - 24, start,
                               tl["shots"][j]["start"] + tl["shots"][j]["duration"] - 0.05, fi * 1.5, fo * 1.5))
        i = j + 1

    # source lines: a short quote and a name, briefly, above the captions
    for s, st in zip(tl["shots"], states):
        src = shot_graphics(pkg, s["shot"]).get("source")
        if src:
            img = source(cfg, src["quote"], src.get("by"), st)
            start = s["start"] + d["source"]["delay"]
            els.append(Element("source", img, safe["left"], d["source"]["bottom"] - img.height + 24, start,
                               min(s["start"] + s["duration"] - 0.2, start + d["source"]["max_seconds"]), fi, fo * 2, rise))

    # end card over the last footage, timed to the closing sentence
    end = pkg.get("end_card") or {}
    end_start = total
    if end.get("lines"):
        cue = tl["shots"][-1]["lines"][-1] if tl["shots"][-1]["lines"] else None
        if cue:
            text = pkg["voiceover"][cue["line"] - 1]["text"]
            last = re.split(r"(?<=[.!?])\s+", text.strip())[-1]
            end_start = cue["end"] - (cue["end"] - cue["start"]) * len(last) / len(text)
        else:
            end_start = tl["shots"][-1]["start"]
        e = title(cfg, end["lines"], d["end_card"])
        if d["end_card"]["scrim"]:
            els.append(Element("scrim", sc, 0, d["canvas"]["height"] - sc.height, end_start - 0.1, total, 0.35, 0))
        els.append(Element("end", e, safe["left"] - 24, d["end_card"]["bottom"] - e.height + 24, end_start, total, fi * 1.5, 0, rise))

    # captions: lower area, never under the hook or the end card
    # A line with its own `caption` gets one punch caption for as long as it is spoken ("" = none);
    # a line without one falls back to reading captions in phrase chunks.
    punched = {n for n, line in enumerate(pkg["voiceover"], 1) if "caption" in line}
    lead = hook_end + 0.05 if hook_lines else 0.0
    for s in tl["shots"]:
        for cue in s["lines"]:
            text = pkg["voiceover"][cue["line"] - 1].get("caption")
            if cue["line"] in punched and text:
                start, stop = max(cue["start"], lead), min(cue["end"] + 0.1, end_start - 0.02)
                if stop - start >= 0.25:
                    img = punch(cfg, text)
                    els.append(Element("caption", img, (W - img.width) // 2, d["punch"]["center_y"] - img.height // 2,
                                       start, stop, d["punch"]["pop"], 0.06, rise))
    for cap in caption_chunks(pkg, tl, cfg, skip=punched):
        start, stop = max(cap["start"], lead), min(cap["end"], end_start - 0.02)
        if stop - start < 0.25:
            continue
        img = caption(cfg, cap["words"])
        els.append(Element("caption", img, (W - img.width) // 2, d["captions"]["center_y"] - img.height // 2, start, stop, fi, 0.06, rise))
    return els, transcript(pkg, tl, cfg)


def transcript(pkg: dict, tl: dict, cfg: dict) -> list[dict]:
    """Every spoken word, in reading-sized chunks, for captions.srt: the platform's caption track
    stays a full transcript even when the on-screen captions are punch lines."""
    return [{"text": c["text"], "start": c["start"], "end": c["end"]} for c in caption_chunks(pkg, tl, cfg, plain=True)]


def punch(cfg: dict, text: str):
    """A punch caption: a few words, large, in the headline face. "A / B" forces the line break."""
    p = _d(cfg)["punch"]
    lines = [x.strip() for x in text.split("/")] if "/" in text else None
    if lines is None:
        words = text.split()
        f = font(cfg, "headline", p["size"])
        if len(words) > 2 and f.getlength(text.replace("*", "").upper()) > p["max_width"]:
            k = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
            lines = [" ".join(words[:k]), " ".join(words[k:])]
        else:
            lines = [text]
    f = fitted(cfg, lines, "headline", p["size"], p["max_width"])
    return text_image(cfg, [marked(cfg, ln.upper(), f) for ln in lines], f.size + p["line_gap"], align="center")


# ---------------------------------------------------------------- compositor
def frames(elements: list[Element], cfg: dict, total: float):
    """One RGBA frame of graphics per video frame, as bytes. Identical frames are reused."""
    from PIL import Image
    c = _d(cfg)["canvas"]
    W, H, fps = c["width"], c["height"], c["fps"]
    faded: dict = {}
    last_key, last = None, None
    for n in range(int(round(total * fps))):
        t = n / fps
        active = []
        for e in elements:
            if not e.start <= t < e.end:
                continue
            a = 1.0
            if e.fade_in and t - e.start < e.fade_in:
                a = (t - e.start) / e.fade_in
            if e.fade_out and e.end - t < e.fade_out:
                a = min(a, (e.end - t) / e.fade_out)
            a = round(max(0.0, min(1.0, a)) * 10) / 10
            ease = 1 - (1 - min(1.0, (t - e.start) / e.fade_in)) ** 2 if e.fade_in and e.rise else 1.0
            active.append((id(e), a, int(round(e.rise * (1 - ease))), e))
        key = tuple(x[:3] for x in active)
        if key != last_key:
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for eid, a, dy, e in active:
                if a <= 0:
                    continue
                img = e.img
                if a < 1:
                    img = faded.get((eid, a))
                    if img is None:
                        img = e.img.copy()
                        img.putalpha(e.img.getchannel("A").point(lambda v, a=a: int(v * a)))
                        faded[(eid, a)] = img
                canvas.alpha_composite(img, (max(0, e.x), max(0, e.y + dy)))
            last_key, last = key, canvas.tobytes()
        yield last


def still(elements: list[Element], cfg: dict, t: float, background=None):
    """The graphics at one moment, over a background if given. For previews and tests."""
    from PIL import Image
    c = _d(cfg)["canvas"]
    data = next(iter(frames([Element(e.name, e.img, e.x, e.y, e.start - t, e.end - t, e.fade_in, e.fade_out, e.rise)
                             for e in elements], cfg, 1 / c["fps"])))
    layer = Image.frombytes("RGBA", (c["width"], c["height"]), data)
    return Image.alpha_composite(background.convert("RGBA").resize(layer.size), layer) if background else layer
