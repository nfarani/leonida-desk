"""Deterministic content-type classification for community posts (Reddit etc.).

Runs before VERIFY. Community content is a lead, never a fact: only a post that points at a concrete,
observable detail in official/verifiable material may support COMMUNITY_DISCOVERY on its own.
Everything is rule-based so the same post always gets the same type.
"""
from __future__ import annotations

import re

from .models import Item, Story
from .text import domain_of

TYPES = ["OBSERVABLE_DISCOVERY", "NEWS_LINK", "RUMOUR", "THEORY", "DISCUSSION", "QUESTION", "MEME",
         "WISHLIST", "OTHER"]
# Never eligible for COMMUNITY_DISCOVERY and, on their own, demand signals rather than stories.
CHATTER = {"DISCUSSION", "QUESTION", "MEME", "WISHLIST"}

_BOILERPLATE = re.compile(r"submitted by\s+/u/\S+|\[link\]|\[comments\]|\[flair:[^\]]*\]|\[links to \S+\]", re.I)
_FLAIR = re.compile(r"\[flair:\s*([^\]]*)\]", re.I)
_URL = re.compile(r"https?://[^\s\]\)]+")
_NOT_NEWS = ("reddit.com", "redd.it", "imgur.com", "x.com", "twitter.com", "youtube.com", "youtu.be",
             "tiktok.com", "discord.gg", "discord.com")

FLAIR_TYPES = [("meme", "MEME"), ("shitpost", "MEME"), ("humor", "MEME"), ("question", "QUESTION"),
               ("discussion", "DISCUSSION"), ("wishlist", "WISHLIST"), ("theory", "THEORY"),
               ("speculation", "THEORY"), ("leak", "RUMOUR"), ("rumo", "RUMOUR")]

_MEME = re.compile(
    r"\bmemes?\b|\bshitpost|\bme (if|when|after|the moment)\b|\b(my|our) (girl|wife|boss|mom|dad)\b.*\b(when|moment)\b"
    r"|\bpov\b|\bbe like\b|\bthose were the days\b|\blmao\b|\blol\b|\bcrazy\b\s*$|😭|😂|🤣|💀", re.I)
_WISH = re.compile(
    r"\bi (really )?(hope|wish)\b|\bhoping\b|\bwish ?list\b|\bit would be (so |really )?(cool|awesome|great|nice)\b"
    r"|\bwouldn'?t (that|it) be\b|\bplease rockstar\b|\bshould (add|bring back|include)\b|\bconcept(ual)?\b"
    r"|\bfan[- ]made\b|\bmy own take\b", re.I)
_WISH_TITLE = re.compile(r"\bi (really )?(want|need)\b", re.I)
# Fan creations and merch photos: not a find, not a claim.
_FAN_MADE = re.compile(
    r"\bi (made|recreated|painted|drew|printed|built|bought)\b|^(made|bought|painted|drew|printed)\b|\bdiy\b"
    r"|\bcustom\b|\bgot .{0,40}\bprinted\b", re.I)
# An observable find needs BOTH a discovery cue and a reference to material anyone can check.
_FIND = re.compile(
    r"\bspot(s|ted)?\b|\b(just )?noticed?\b|\bdiscover(ed|y)?\b|\bfound\b(?! out|( \w+){0,2} (shop|store|place|copy))|\bsmall detail\b|\bhidden detail\b"
    r"|\bdetail (i|we|nobody|no one) (haven'?t|hasn'?t|missed)\b|\bhaven'?t seen (anyone |anybody |it )?(mention|talk|post)"
    r"|\beaster egg\b|\bif you (look|zoom|pause)\b|\blook closely\b|\bzoom(ed|ing)? in\b|\bfreeze[- ]frame\b"
    r"|\bin the background\b|\bcorrected\b|\bquietly (changed|updated|added|removed)\b|\bnow (shows|lists|says)\b"
    r"|\bwas (changed|updated|removed|added)\b", re.I)
_MATERIAL = re.compile(
    r"\btrailers?\b|\bscreenshots?\b|\bextended look\b|\bkey ?art\b|\bartwork\b|\bfootage\b|\bgameplay (video|reveal)\b"
    r"|\bthumbnails?\b|\bframes?\b|\bwebsite\b|\brockstargames\b|\bnewswire\b|\bstore (page|listing)\b|\bpsn\b"
    r"|\bps store\b|\blisting\b|\bpatch notes\b|\bmagazine\b|\bissue of\b|\bgame informer\b|\bmurals?\b"
    r"|\bbillboards?\b|\bbanner\b|\bbox ?art\b|\bcover\b|\bofficial (site|page|art|image|images|photo|photos)\b"
    r"|\bsource code\b|\bapi\b|\bfile size\b", re.I)
_FIND_TITLE = re.compile(r"\bin the (new |latest |same |second |first )?(screenshots?|trailers?|extended look|key ?art)\b", re.I)
_THEORY = re.compile(
    r"(?<!in )\btheor(y|ies)\b|\bconspiracy\b|\banyone else (think|feel|notice)\b|\bcould mean\b|\bwhat if\b"
    r"|\bpredict(ion|ions|ing)?\b|\bhot take\b|\bhints? at\b|\bhow i think\b|\bmy guess\b", re.I)
# Weaker interpretation cues only count in the title; in a body they are ordinary conversation.
_THEORY_TITLE = re.compile(
    r"\bi (don'?t )?think\b|\bcould be\b|\bmight (mean|be (a|the|for))\b|\bi (bet|suspect|believe)\b"
    r"|\bconveniently\b|\bsuspicious(ly)?\b", re.I)
_RUMOUR = re.compile(
    r"\bleak(s|ed)?\b|\brumou?rs?\b|\binsider\b|\ballegedly\b|\bdatamin(e|ed|er)\b|\breportedly\b"
    r"|\bunconfirmed\b|\bconfirmed\b|\bsources? (say|says|claim|claims)\b|\baccording to\b", re.I)
_QUESTION_START = re.compile(
    r"^(what|which|who|whom|whose|how|why|when|where|is|are|am|do|does|did|will|would|can|could|should|has|have"
    r"|anyone|anybody|any)\b", re.I)
_DISCUSSION = re.compile(
    r"\bthoughts\b|\bopinions?\b|\bwhat do (you|we|y'?all)\b|\bexcited\b|\bhyped?\b|\bcan'?t wait\b"
    r"|\bmy (only|biggest|favou?rite|top)\b|\bi feel\b|\bfeels? like\b|\bi'?m (so|taking|planning|glad|worried)\b"
    r"|\bcomplaint\b|\bnit-?pick\b|\bunpopular\b|\btop \d+\b|\bfavou?rite\b|\bplans?\b|\bdiscussion\b", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _BOILERPLATE.sub(" ", text.replace("’", "'"))).strip()


def _near(a: re.Pattern, b: re.Pattern, text: str, window: int = 90) -> bool:
    """A discovery cue only counts next to the material it refers to."""
    spans = [m.span() for m in b.finditer(text)]
    return any(abs(m.start() - s) <= window or abs(m.end() - e) <= window
               for m in a.finditer(text) for s, e in spans)


def _links_to_news(item: Item, cfg: dict) -> bool:
    from .normalise import classify_domain
    registry = cfg["sources"]["domains"]
    for url in _URL.findall(item.snippet):
        dom = domain_of(url)
        if not dom or any(dom == d or dom.endswith("." + d) for d in _NOT_NEWS):
            continue
        hit = classify_domain(dom, registry)
        if hit and hit[0] in ("primary", "journalism"):
            return True
    return False


def linked_urls(item: Item) -> list[str]:
    return _URL.findall(item.snippet)


def classify_post(item: Item, cfg: dict) -> str:
    """Content type for one community item. Order matters: the first matching rule wins."""
    title = _clean(item.title)
    body = _clean(item.snippet)
    text = f"{title} {body}"
    is_question = title.endswith("?") or bool(_QUESTION_START.match(title))
    flair = (_FLAIR.search(item.snippet) or [None, ""])[1].lower()
    for needle, ctype in FLAIR_TYPES:
        if needle in flair:
            return ctype
    if _links_to_news(item, cfg):
        return "NEWS_LINK"
    if _MEME.search(title):
        return "MEME"
    if _WISH.search(text) or _WISH_TITLE.search(title):
        return "WISHLIST"
    if _FAN_MADE.search(title):
        return "OTHER"
    if not title.endswith("?") and (_near(_FIND, _MATERIAL, text) or
                                    (_FIND_TITLE.search(title) and not _QUESTION_START.match(title))):
        return "OBSERVABLE_DISCOVERY"
    if _THEORY.search(text) or _THEORY_TITLE.search(title):
        return "THEORY"
    if is_question:
        return "QUESTION"
    if _RUMOUR.search(text):
        return "RUMOUR"
    if _DISCUSSION.search(text):
        return "DISCUSSION"
    return "OTHER"


def content_type(item: Item, cfg: dict) -> str | None:
    """Cached content type; None for non-community items."""
    if item.source_type != "community":
        return None
    if not item.content_type:
        item.content_type = classify_post(item, cfg)
    return item.content_type


def community_types(story: Story, cfg: dict) -> list[str]:
    return [t for t in (content_type(i, cfg) for i in story.items) if t]


def is_community_only(story: Story) -> bool:
    return all(i.source_type == "community" for i in story.items)


def is_chatter_only(story: Story, cfg: dict) -> bool:
    """True when a story is nothing but discussion/question/meme/wishlist posts."""
    return is_community_only(story) and all(t in CHATTER for t in community_types(story, cfg))
