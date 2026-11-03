"""Event fingerprints: decide whether two headlines describe the same underlying event.

Token similarity alone misses rewrites ("rating pulled after revealing sex scenes" vs "PEGI removes
rating after explicit-content details appear"). A fingerprint adds named entities, topic concepts,
headline stems, linked URLs and publication time. Every rule needs two independent signals, so
stories that merely share "Rockstar" or "GTA 6" stay apart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from .community import linked_urls
from .models import Item, Story
from .text import STOPWORDS, canonical_url, similarity, tokens

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*")
_ACRONYM = re.compile(r"\b[A-Z]{3,6}\b")
_RANK = {None: 0, "borderline": 1, "same": 2}


@dataclass
class Feat:
    toks: set[str]
    entities: set[str]
    concepts: set[str]
    stem: tuple[str, ...]
    when: datetime
    url: str
    links: set[str] = field(default_factory=set)


@dataclass
class Relation:
    verdict: str | None      # "same" | "borderline" | None
    score: float
    reason: str = ""


def _is_title_case(title: str) -> bool:
    words = [w for w in _WORD.findall(title) if len(w) > 3]
    return len(words) < 4 or sum(w[0].isupper() for w in words) / len(words) > 0.6


def _phrases(title: str) -> set[str]:
    """Runs of 2+ capitalised words, plus acronyms, from sentence-case headlines only.
    Title Case and shouty headlines capitalise everything, so they tell us nothing."""
    if _is_title_case(title):
        return set()
    out = {m.group(0).lower() for m in _ACRONYM.finditer(title)}
    for chunk in re.split(r"[:;,.!?\"“”‘()\[\]|–—]| - ", title):
        run: list[str] = []
        for w in chunk.split() + [""]:
            w = re.sub(r"['’]s$", "", w.strip("'’"))
            if w and w[0].isupper() and w.isalpha():
                run.append(w.lower())
                continue
            if run and run[0] in STOPWORDS:
                run = run[1:]           # sentence-initial "Why", "The", "How"
            if len(run) >= 2:
                out.add(" ".join(run))
            run = []
    return out


class Fingerprinter:
    """Builds the entity lexicon once per run, then fingerprints items."""

    def __init__(self, cfg: dict, items: list[Item]):
        c = cfg["settings"]["clustering"]
        self.thr, self.floor = c["similarity_threshold"], c["borderline_floor"]
        self.window_h = c.get("event_window_hours", 96)
        generic = {g.lower() for g in c.get("generic_entities", [])}
        self.aliases: list[tuple[re.Pattern, str]] = []
        for canon, names in (c.get("entities") or {}).items():
            for n in names:
                self.aliases.append((re.compile(rf"\b{re.escape(n.lower())}\b"), canon))
        self.concepts = {name: re.compile("|".join(rf"(?<![a-z]){re.escape(p.lower())}(?![a-z])" for p in pats))
                         for name, pats in (c.get("concepts") or {}).items()}
        known = {n.lower() for names in (c.get("entities") or {}).values() for n in names}
        dynamic = set()
        for it in items:
            for ph in _phrases(it.title):
                if ph in generic or all(w in generic or w in STOPWORDS for w in ph.split()):
                    continue
                dynamic.add(ph)
        self.dynamic = [(re.compile(rf"\b{re.escape(ph)}\b"), ph) for ph in sorted(dynamic - known)]
        self._cache: dict[int, Feat] = {}
        self._pairs: dict[tuple[int, int], Relation] = {}

    def feat(self, it: Item) -> Feat:
        f = self._cache.get(id(it))
        if f is None:
            low = it.title.lower().replace("’", "'")
            ents = {canon for pat, canon in self.aliases if pat.search(low)}
            covered = [pat for pat, canon in self.aliases if pat.search(low)]
            for pat, ph in self.dynamic:
                if pat.search(low) and not any(c.search(ph) for c in covered):
                    ents.add(ph)
            head = re.split(r":| - | – | — |\|", low)[0]
            f = Feat(toks=tokens(it.title), entities=ents,
                     concepts={n for n, pat in self.concepts.items() if pat.search(low)},
                     stem=tuple(sorted(tokens(head))), when=it.when, url=canonical_url(it.url),
                     links={canonical_url(u) for u in linked_urls(it)})
            self._cache[id(it)] = f
        return f

    def relate(self, a: Item, b: Item) -> Relation:
        key = (id(a), id(b)) if id(a) < id(b) else (id(b), id(a))
        if key not in self._pairs:
            self._pairs[key] = self._relate(a, b)
        return self._pairs[key]

    def _relate(self, a: Item, b: Item) -> Relation:
        fa, fb = self.feat(a), self.feat(b)
        if fa.url in fb.links or fb.url in fa.links:
            return Relation("same", 2.0, "post links to the article")
        sim = similarity(fa.toks, fb.toks)
        shared_ent = fa.entities & fb.entities
        shared_con = fa.concepts & fb.concepts
        if fa.entities and fb.entities and not shared_ent:
            sim = round(sim * 0.75, 4)      # different named subjects (Dan vs Sam Houser, PEGI vs Australia)
        if sim >= self.thr:
            return Relation("same", 1 + sim, f"headline similarity {sim:.2f}")
        near = abs((fa.when - fb.when).total_seconds()) <= self.window_h * 3600
        if near:
            if len(fa.stem) >= 4 and fa.stem == fb.stem:
                return Relation("same", 1.9, "same headline, syndicated")
            if shared_ent and (shared_con or sim >= 0.2):
                what = ", ".join(sorted(shared_ent | shared_con))
                return Relation("same", 1.5 + sim, f"same subject and topic ({what})")
            if len(shared_con) >= 2:
                return Relation("same", 1.4 + sim, f"same topics ({', '.join(sorted(shared_con))})")
        if sim >= self.floor:
            return Relation("borderline", sim, f"headline similarity {sim:.2f}")
        if near and shared_ent:
            return Relation("borderline", 0.25 + sim, f"same subject ({', '.join(sorted(shared_ent))})")
        if near and shared_con and sim >= 0.1:
            return Relation("borderline", 0.2 + sim, f"same topic ({', '.join(sorted(shared_con))})")
        return Relation(None, sim)

    def relate_story(self, item: Item, story: Story, only=None) -> tuple[Relation, int, int]:
        """(best relation, how many of the story's items are the same event, how many were compared)."""
        best, same, n = Relation(None, 0.0), 0, 0
        for other in story.items:
            if other is item or (only is not None and not only(other)):
                continue
            n += 1
            r = self.relate(item, other)
            same += r.verdict == "same"
            if (_RANK[r.verdict], r.score) > (_RANK[best.verdict], best.score):
                best = r
        return best, same, n
