"""Text utilities: URL canonicalisation, HTML stripping, tokenisation, similarity."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "fbclid", "gclid", "ref", "ref_src", "cmpid", "taid"}

STOPWORDS = set("""
a an the and or but of to in on at for with from by as is are was were be been it its this that these
those you your we our they their he she his her them i me my not no yes so if than then there here
what which who whom whose how why when where will would can could should may might just now new more
most all any some about into over after before up down out off again also very vs via get got has have
had do does did one two first finally really like actually look looks looking make makes making made
say says said still even way much thing things going see sees
""".split())
# Tokens shared by nearly every item -> carry no information for dedup
GENERIC = {"gta", "vi", "6", "gta6", "gtavi", "grand", "theft", "auto", "rockstar", "game", "games",
           "gaming", "news", "report", "fans", "fan", "update", "everything", "know", "need", "here",
           "release", "date", "latest", "details", "detail"}
_NUM = re.compile(r"^\d+$")


def canonical_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _TRACKING]
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def domain_of(url: str) -> str:
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return ""
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def strip_html(text: str | None, limit: int = 600) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def strip_publisher_suffix(title: str, publisher: str | None = None) -> str:
    """'Big news - IGN' -> 'Big news' (Google News appends publisher)."""
    title = title.strip()
    if publisher and title.endswith(publisher):
        title = title[: -len(publisher)].rstrip(" -|–—")
    else:
        title = re.sub(r"\s[-|–—]\s[^-|–—]{2,40}$", "", title)
    return title.strip()


def _stem(tok: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(tok) > 4 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def tokens(text: str) -> set[str]:
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    raw = re.findall(r"[a-z0-9]+", text)
    out = set()
    for t in raw:
        if t in STOPWORDS or t in GENERIC or (len(t) < 2 and not _NUM.match(t)):
            continue
        out.add(_stem(t))
    return out


def similarity(a: set[str], b: set[str]) -> float:
    """Blend of Jaccard and overlap coefficient, penalised when numbers conflict."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    jac = inter / len(a | b)
    ovl = inter / min(len(a), len(b))
    sim = 0.5 * jac + 0.5 * ovl
    na = {t for t in a if _NUM.match(t)}
    nb = {t for t in b if _NUM.match(t)}
    if na and nb and not (na & nb):
        sim *= 0.7          # "Trailer 2" vs "Trailer 3" are different stories
    if inter < 2:
        sim *= 0.75         # one shared word is never enough on its own
    return round(sim, 4)
