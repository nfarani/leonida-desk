# CLAUDE.md: Leonida Desk

This file is the operating manual for every Claude agent working in this repository. Read it fully
before doing anything. When this file conflicts with a request, raise the conflict with the operator.

---

## 1. Mission

**Leonida Desk is a news research desk** (operator decision, 21 October 2026; it was a video-first
short-form brand). Its product is the **daily hot list**: the hottest stories in games right now,
**Grand Theft Auto VI first, then gaming broadly**, scored, ranked and honestly labelled. The newsroom
answers, every day:

> **"What are the hottest GTA VI and gaming stories right now, and how do they rank?"**

- **Ten stories a day by default; the operator can ask for more** (`/morning 20`, `/morning 30`,
  `scripts/morning.py --count N`). The number is a target, not permission to pad: a story that is
  stale, unsupported speculation or a duplicate never takes a slot. If fewer stories qualify the list
  says so.
- **Hot** means fresh, carried by credible outlets, gaining coverage and significant to players or the
  industry. Ranking uses the hot score (section 6).
- **GTA VI is the flagship** and gets a ranking bonus, but the list must not become GTA-only because
  GTA sources are better configured.
- **No videos unless the operator asks for one.** The video tooling (section 14) is dormant: it is
  never proposed, planned or mentioned in the daily briefing. When the operator asks for a video of a
  specific story, `/make <rank | story:ID>` still works and its rules still apply.
- **Articles only on request** (section 13). The hot list does not propose articles.
- **Product and tech news** (`lane: tech` feeds, operator decision 11 Oct 2026) is listed separately
  under the hot list and is not scored with gaming. A tech item that attaches to a gaming story is
  just another source. The same evidence and label rules apply.

**Where this is going** (not built until the operator asks): a general research and news engine:
relevant general news, historical research, marketing articles, and whatever else the operator
points it at. Build for gaming today; do not add speculative infrastructure for those verticals.

The name is fixed; do not rename the publication without the operator's approval.

A human operator is **Editor-in-Chief**. The system researches and recommends; the editor decides.
**Nothing is published, generated or posted without the editor's explicit approval.** The switches for
automatic publishing, video generation, social posting, ads and deployment are in `config/flags.yaml`
and `config/publishing.yaml` and are off; do not turn one on unless the operator explicitly asks.

**The website is frozen** (section 13). Touch it only to publish an article the operator asked for or
to fix a critical bug.

Value comes from being **early, accurate and original**: finding stories before others, labelling
them honestly and giving each one a distinct angle. It never comes from volume.

---

## 2. Editorial standards (non-negotiable)

1. **Do not invent facts.** Every claim must trace to a stored source item.
2. **Do not invent sources.** A URL is only valid if it came from a feed or from a web-search tool
   result. Never type a URL from memory. Never cite an outlet that wasn't in the results.
3. **Do not fabricate quotes.** Paraphrase. If an exact quote matters, it must be verbatim from a source.
4. **Never upgrade a rumour.** A rumour, leak, theory or community find is never described as confirmed,
   in a headline, hook, summary or caption.
5. **One story, one recommendation.** Multiple outlets covering one event = one story. Do not split a
   story into several recommendations to pad output.
6. **Original work only.** AI-generated content must still contain real research, editorial judgement,
   storytelling and creative treatment. We do not re-voice other creators' videos or articles.
7. **No spam optimisation.** No misleading thumbnails/hooks the content cannot deliver, no engagement
   bait built on false claims, no flooding.
8. **Do not rely on model memory for current facts.** Release dates, prices, trailer counts and
   platform details change. State them only from sources fetched in the current run.

---

## 3. Freshness requirements

Freshness is the single highest-weighted factor (20/100) and the reason this system exists.

- Freshness decays with a **half-life** (`config/settings.yaml → freshness.half_life_hours`, default 18h)
  measured from the earliest known publication of the story.
- A **material update** refreshes freshness for `update_bump_hours`. A material update is the story's
  first official source, its first tier-1 source, or a verification label change caused by new
  evidence. Another outlet rewriting or syndicating a story we already have is not one, and neither
  is a label change caused by merging duplicates or reclassifying a post.
- A story with no publication date on any source is held back: its freshness cannot be assessed.
- Discovery ignores items older than `max_item_age_hours` (7 days).
- Every briefing shows **published time** and **first-discovered time** for each story. If those are far
  apart, we were late. That is a signal to add sources.
- Saturation is scored separately: a story can be fresh *to us* but already crowded.

---

## 4. Verification policy

Every story carries **exactly one** label:

| Label | Meaning | Minimum evidence (enforced in code) |
|---|---|---|
| `CONFIRMED` | Official statement by Rockstar, Take-Two, PlayStation or Xbox | ≥1 **primary** source item attached |
| `HIGH_CONFIDENCE_REPORT` | Tier-1 outlet with own sourcing, or multiple tier-1 outlets | ≥1 tier-1 journalism item |
| `CREDIBLE_RUMOUR` | Unconfirmed, carried by credible journalism / proven insider | ≥1 journalism item |
| `COMMUNITY_DISCOVERY` | Observable find in official material; interpretation unverified | any |
| `THEORY` | Reasoned community interpretation | any |
| `SPECULATION` | Unsourced, wishlist, low-credibility leak | any |
| `FALSE_OR_DEBUNKED` | Officially denied or credibly disproven: **debunk content only** | primary or tier-1 support |

Rules:
- **Evidence ceilings are hard-coded** in `research/verify.py`. Claude may choose a *lower* label but
  can never exceed the ceiling. If in doubt, choose the lower-confidence label.
- **Community content is a lead, never a fact.** Reddit/GTAForums/YouTube/X items alone can never be
  above `COMMUNITY_DISCOVERY`, and only a post classified as an observable discovery (a concrete,
  checkable detail in official or verifiable material) can reach it. Discussion, questions, memes and
  wishlists top out at `THEORY`, are labelled `SPECULATION` by the heuristic, and are not recommended
  on their own: they only add demand to stories they attach to.
- Journalism reporting "Rockstar announced X" without the primary item attached is
  `HIGH_CONFIDENCE_REPORT`. To reach `CONFIRMED`, find and attach the primary source.
- Hooks for anything below `HIGH_CONFIDENCE_REPORT` must be hedged; un-hedged hooks are auto-prefixed
  `[UNCONFIRMED]`.
- Every recommendation shows its label badge and a risk/caveat line.

Source tiers live in `config/sources.yaml → domains`: tier 0 official · 1 top journalism ·
2 solid journalism · 3 low-quality/unknown · 4 community. Unknown domains default to tier 3.

---

## 5. Pipeline

```
DISCOVER → NORMALISE → CLUSTER → VERIFY → SCORE → RANK → HOT LIST → SAVE       (the daily desk, built)
PACKET → DRAFT → CHECK → GATE → APPROVE → PUBLISH (local)                      (articles, on request; section 13)
/make → /render → edit → approve → post → /published                           (video, dormant; on request only; section 14)
DEPLOY                                                                         (adapters stubbed, manual only)
```

| Stage | Module | What it does |
|---|---|---|
| DISCOVER | `research/discover/` | RSS/Atom feeds, Google News site-restricted searches, Reddit JSON (RSS fallback), Claude web search. Fetchers never raise; failures are reported in the briefing. |
| NORMALISE | `research/normalise.py` | Canonical URLs, publisher classification by domain, relevance filter, scope filter (film, TV, celebrity, shopping, listicles, guides and reviews are rejected even when they name a game), age filter, URL dedup, engagement refresh. The same scope filter holds back stories already stored. |
| CLUSTER | `research/cluster.py`, `research/fingerprint.py` | Attaches items to stories and merges duplicate stories using an event fingerprint (headline similarity, named subjects, topic concepts, syndicated headlines, linked URLs, time window). A merge needs agreement from a share of the items on both sides. Borderline pairs go to Claude when available, otherwise they are reported. |
| CLASSIFY | `research/community.py` | Deterministic content type for every community post (observable discovery, news link, rumour, theory, discussion, question, meme, wishlist, other). |
| VERIFY | `research/verify.py` | Heuristic label within evidence ceiling. |
| SCORE | `research/score.py` + `research/llm.py` | Computed dims (freshness, demand, novelty, credibility), judged dims (Claude or heuristic), viral score, saturation. |
| TAG | `research/games.py` | Game and franchise from `config/games.yaml`; parent event (the interview, cover story or showcase several outlets are relaying). |
| RANK | `research/rank.py` | Cooldown filter, saturation penalty, topic penalty, flagship bonus. |
| HOT LIST | `research/recommend.py`, `research/desk.py` | Story type (breaking, discovery, developing, background), momentum, confidence, skip reasons, the top N by hot score with duplicate and topic caps, the radar, POST NOW flags. Fills every editorial field honestly. |
| SAVE | `research/db.py`, `research/report.py` | SQLite + Markdown/JSON briefing in `outputs/briefings/`. |

**Web-search lane anti-hallucination rule:** only URLs/titles inside `web_search_tool_result` blocks are
accepted. Model prose never becomes a source.

**Graceful degradation:** without `ANTHROPIC_API_KEY` the pipeline runs on feeds + heuristics and says so
at the top of the briefing.

---

## 6. Scoring

Weights in `config/scoring.yaml` (must total 100; news weighting, operator decision 21 Oct 2026):

| Dimension | Weight | Method |
|---|---|---|
| Freshness | 20 | computed: half-life decay |
| Existing demand | 15 | computed: Reddit engagement ⊕ outlet velocity (24h) |
| Significance | 15 | judged: how much it matters to players or the industry |
| Curiosity gap | 10 | judged |
| Surprise | 10 | judged |
| Credibility | 10 | computed: from verification label |
| Emotional reaction | 8 | judged |
| Novelty | 7 | computed: 1 − similarity to stories we used in last 14 days |
| Shareability | 3 | judged |
| Comment potential | 2 | judged |

- **opportunity_score** (0–100) = Σ weight × dimension.
- **viral_score** (0–100) = weighted blend of curiosity, surprise, emotion, shareability, comments, demand.
- **saturation_score** (0–100, higher = more crowded) = outlet count + story age + competitor YouTube
  videos in 48h (if `YOUTUBE_API_KEY`).
- **hot score** (`rank_score`) = opportunity × (1 − 0.35 × saturation/100) + flagship bonus − topic
  penalty. The hot list is ordered by it; the briefing shows it next to opportunity.
- **momentum** (0-100): distinct publishers in the last 6h plus existing demand.
- **recommendation_confidence** (0-100): how far to trust the ranking of a story (Claude or heuristic
  judgement, label, best source, corroboration, real text; halved by a conflict between sources).
- **search_score** and **commercial_score** (0–100) are rule-based estimates (`research/desk.py`). They
  are not measured demand or revenue and never change a label or a rank.
- **Flagship bonus:** stories about a flagship game get `ranking.flagship_bonus` rank points.
- **POST NOW** (max 3): opportunity ≥ 55, freshness ≥ 0.45, saturation ≤ 65, label not THEORY/SPECULATION.
  It marks fresh, credible news that is not yet crowded.

### The hot list
`config/settings.yaml → ranking.hot_list`. The top `count` stories (default 10, any run can ask for
more with `--count N` or `/morning N`), then `radar` more as one-liners. A story never takes a slot if:

- it is held back (cooldown, no publication date, community chatter, out of scope, stale);
- its label is in `excluded_labels` (SPECULATION), or it is single-source speculation;
- its freshness is below `min_freshness` (about 50 hours): it is not hot;
- it is the same story as one already listed (same game, similar headline and at least
  `duplicate_min_shared_words` meaningful shared words): it is listed under the first;
- one parent event or one running topic (`topic_caps`, e.g. console hacking, layoffs) already has
  `ranking.max_per_parent_event` slots: it is listed as a further angle.

The count is a target, not a quota. If fewer stories qualify the list says so, and when none do it says
**NO HOT STORIES RIGHT NOW.** Never promote a story to fill a slot. Claude judges at least twice as many
candidates as the list holds; its judgement of a story is stored and reused until the story gains a
source.

Judged dimensions are **subjective by design** and are always shown with "Scored by: claude|heuristic".

---

## 7. Deduplication & cooldown

- Items about the same underlying event cluster into **one story** (`similarity_threshold` 0.45 on
  blended Jaccard/overlap; numbers that conflict, e.g. "Trailer 2" vs "Trailer 3", are penalised).
- When the editor publishes a story (`scripts/mark_used.py`), it enters a **72-hour cooldown**. It
  returns only if a **meaningful new development** occurs (a material update as defined in section 3).
- Duplicate stories already in the database are merged: sources move to the surviving story and the
  absorbed row is kept as an empty tombstone (status `stale`, "merged into story #N").
- Other stories in the same `content_cluster` get a small penalty (not exclusion) for 72h.
- `--reject` permanently removes a story from recommendations.

---

## 8. Data model (SQLite, `data/schema.sql`)

- **sources**: publishers (domain, type, tier).
- **content_clusters**: editorial categories (see `config/categories.yaml`), with `last_used_at`.
- **stories**: one row per underlying event: headline, summary, best source_url/name/type,
  published_at, first_seen_at, last_updated_at, last_material_update_at, verification_status,
  content_cluster, freshness/viral/saturation/opportunity scores, score_breakdown (JSON), reasoning,
  status (`new|recommended|used|rejected|stale`), used_at.
- **story_sources**: every article/post/result attached to a story, with engagement JSON.
- **runs**: each briefing run with diagnostics.
- **recommendations**: rank, scores, POST NOW flag, why_care, format, angle, hook, risk, editorial
  bucket and recommended output per run.
- **published_content**: what the editor actually published (drives cooldown).
- **performance_metrics**: legacy, unused. Video numbers live in **video_posts** and **video_metrics**;
  operator ratings in **story_ratings**. Stories also store their latest desk view and Claude's judgement.

---

## 9. Agent behaviour

Agent specs live in `agents/` (mirrored to `.claude/agents/` for Claude Code). Commands live in
`commands/` (mirrored to `.claude/commands/`). Run `scripts/sync_claude.sh` after editing either.

All agents:
- Prefer running the pipeline over improvising. The pipeline is auditable; ad-hoc chat research isn't.
- When adding anything to a briefing by hand, include a real URL you actually opened, and a label.
- Flag uncertainty plainly. "Unclear" is an acceptable answer; a confident wrong answer is not.
- Never edit verification ceilings, scoring weights or cooldown rules without the operator asking.
- Keep the briefing scannable: the editor should be able to decide in under five minutes.

---

## 10. Repository map

```
CLAUDE.md            this file
agents/              agent role specs (research scout, verifier, briefing editor, article writer)
commands/            daily: /morning [N] /top /story /ideas /watchlist /rate
                     on request: /article /approve-article · video (dormant): /make /render /video /videos
                     /revise-video /published /analytics      system: /sources /status
config/              settings, sources, scoring, verification, categories, publishing, evergreen,
                     games (registry), flags (feature flags), affiliates (products)
data/                schema.sql + SQLite database (git-ignored) + evidence/ (evidence packets, kept)
research/            the pipeline package (see sections 5 and 13)
scripts/             CLI entry points: morning, make_video, perf, article, approve_article, publish_article, ...
site/                the publication (Astro). Articles live in site/src/content/articles/
outputs/briefings/   generated briefings (latest.md always = newest)
outputs/videos/      one folder per video: package.json (the source) plus brief.md, script.md,
                     storyboard.json, higgsfield-prompts.json, evidence.json, social-copy.md, status.json, assets/
docs/                screenshots and notes
analytics/           placeholder for ANALYSE/LEARN
tests/               offline tests on synthetic .test-domain data
```

## 11. Common commands

```bash
pip install -r requirements.txt
cp .env.example .env               # add ANTHROPIC_API_KEY
python scripts/check_sources.py    # verify feeds live; flip verified: true in sources.yaml
python scripts/morning.py          # run the pipeline → the top 10 in outputs/briefings/latest.md
python scripts/morning.py --count 30   # the top 30 instead
python scripts/desk.py top -n 20   # the latest hot list, then the radar
python scripts/mark_used.py --rank 1 --platform site --url <url>   # we covered it: 72h cooldown
python scripts/article.py packet 3      # start an evidence packet for recommendation rank 3
python scripts/article.py check <slug>  # fact-check, score and gate a draft
python scripts/approve_article.py <slug>
python -m pytest -q
cd site && npm install && npm run preview:drafts   # read drafts locally; npm run build = published only
```

The video loop, only when the operator asks for a video:

```bash
python scripts/make_video.py init 1                     # package for hot list rank 1 (or story:<id>)
python scripts/make_video.py check <video_id>           #    validate, write the project files
python scripts/make_video.py plan <video_id>            # 3. scenes, generations, estimated cost
python scripts/make_video.py produce <video_id>         #    the production plan and its cost; add --confirm to run it
                                                        #    -> final.mp4 in the package, status READY_FOR_REVIEW
python scripts/make_video.py approve <video_id>         # 4. after the edit is reviewed
python scripts/make_video.py publish <video_id> --platform youtube_shorts --url <url>   # 5. log the post
python scripts/perf.py log <video_id> youtube_shorts --checkpoint 24h --views N ...     # 6. log the numbers
python scripts/perf.py rate <story id> GOOD             # calibration: your rating against the system's
python scripts/perf.py review                           # the 10-video review
python scripts/desk.py status                           # keys, feeds, flags, what is not configured
```

If `python` is not on PATH, use the project virtualenv: `.venv/bin/python`.

## 12. Roadmap (do not build until asked)

- **Research engine beyond gaming:** relevant general news, historical research, marketing articles
  and other verticals the operator names. Each would need its own sources, relevance rules, categories
  and scoring weights. Not before the operator asks.
- **Calibration:** operator ratings (`/rate`) are compared with the system's scores to find systematic
  scoring mistakes. Never rewrite scoring weights automatically from a small dataset.
- **Source expansion:** authenticated Reddit access (unauthenticated requests are rate-limited),
  YouTube trend data (`YOUTUBE_API_KEY`), more official developer feeds.
- **Dormant:** video production (section 14), Higgsfield API validation, long-form YouTube.
- **Frozen:** deployment adapters, newsletter and analytics providers, accounts, comments, reactions.

---

## 13. Articles and publication (on request only)

The hot list does not propose articles. When the operator asks for one, `/article <rank | story:ID>`
writes it from an evidence packet under the rules below. Story types on the hot list (`research/desk.py`,
thresholds in `config/publishing.yaml → buckets`): **Breaking** (new, with journalism or an official
source), **Discovery** (a community find or theory), **Developing** (known and well sourced, no longer
fresh), **Background** (reference content). Never relabel a story's type to make it look newer.

### Evidence-first writing (non-negotiable)
- An article is written from an **evidence packet** (`data/evidence/<packet>.json`): stored sources,
  and claims each tied to one source, with its URL, date, verification level and a paraphrase.
- Open a source in the current session before citing it. Only stored sources may be cited.
- Every paragraph that states a fact cites its claims (`[^c12]`). Quotes are verbatim or not used.
- Explanation, analysis and comparison go under an analysis heading and may not introduce facts,
  numbers, quotes or attributions that are missing from the packet.
- Never fabricate quotes, release information, mechanics, characters, locations, developer statements
  or statistics. Model memory is not a source, including for comparisons with earlier games.
- An article's label never exceeds its story's label.

### Originality
We do not publish rewrites. An article must add synthesis, comparison, context, a timeline, a fact
check, a structured reference or a clear explanation. `originality_score` (0-100) measures this, and a
draft that mostly repeats its sources is blocked.

### Publication gate (`research/articles.py`, deterministic)
- `DO_NOT_PUBLISH`: speculation, unsupported or unverifiable claims, a thin story (fewer than
  `article.min_claims` verified claims), a rewrite, a duplicate, very low quality.
- `REVIEW_REQUIRED`: rumours, theories, community discoveries, unresolved conflicts between sources,
  cited sources that were not opened, sensitive claims, uncertain media rights, or any auto-publish
  threshold not met.
- `AUTO_PUBLISH_ELIGIBLE`: label ≥ `HIGH_CONFIDENCE_REPORT`, originality ≥ 70, quality ≥ 75, no
  unresolved conflicts, and two independent credible sources or one primary source.
  **Eligible does not mean published**: while `gate.auto_publish.enabled` is false, the article is
  still `REVIEW_REQUIRED`.

Article statuses: `DRAFT` → `REVIEW_REQUIRED` → `APPROVED` → `PUBLISHED`, or `REJECTED`.
`/article` ends at DRAFT or REVIEW_REQUIRED. `/approve-article` re-runs every check and the site build
and sets APPROVED. `scripts/publish_article.py` sets PUBLISHED, a local status change. Deployment is a
separate, manual step.

### Dates and SEO
- `published_at` is set once and never changed. `updated_at` moves only when the text changes.
  Never alter a date to make an article look fresh.
- Technical SEO only: canonical URLs, sitemap, RSS, robots.txt, Open Graph, structured data, internal
  links. No keyword stuffing, no target word counts, no near-identical pages, no pages made to chase
  keyword variations.

### Authorship
Articles carry the publication byline from `config/publishing.yaml`. Never invent a journalist, a
credential or a biography. The site's AI and automation disclosure must stay accurate: update it when
the way automation is used changes.

### Games
`config/games.yaml` is the registry behind story tagging and `/games/<slug>/`. Aliases only decide
which stories belong to a game. Every factual field (developer, publisher, platforms, release date,
summary) must come from a stored source listed under `sources`; leave it null rather than fill it
from memory. A game page shows only the facts that are filled in.

### Site
The site is the simple first version (reverted on 7 October 2026 at the operator's request): Home,
Latest, News, Discoveries, Explainers, Guides, Tech (articles with `section: tech` in their front matter;
added 11 Oct 2026), the article page, About, Editorial standards, the AI
disclosure and a Privacy page, plus RSS, sitemap and robots.txt. It describes itself as a gaming news
blog with a close focus on GTA VI and a product news desk. It has no ads, affiliate blocks, newsletter form, games
pages, reviews, videos page, contact or privacy pages and no analytics script. The expanded version is
kept in `site-archive/expanded-2026-10-05/`; do not bring any of it back unless the operator asks.
The site needs Node 22.12 or newer to build.

**The site is live** at the address in `config/publishing.yaml → publication.site_url` (Cloudflare, deployed
as a Workers static site from `site/`, project `leonida-desk`). To put published articles on the web run
`scripts/deploy_site.sh`: it builds the production site with the real address and deploys it. Deploying is
outward-facing: do it only when the operator asks, never deploy a preview build, and never deploy an
article that is not PUBLISHED. When a domain is attached, change `site_url` and redeploy.

`site/` is an Astro project. A production build (`npm run build`) contains PUBLISHED articles only.
`npm run preview:drafts` also shows drafts for the editor, marked noindex (the flag is fixed at config
time in `astro.config.mjs`, because the Cloudflare adapter does not pass the shell environment to pages). Never deploy a preview build.

---

## 14. Short-form video (`/make`, `/render`): DORMANT

**Operator decision, 21 Oct 2026: no videos unless the operator asks for one.** Nothing in this section
runs, is proposed or is mentioned in the daily briefing. When the operator asks for a video of a
specific story, every rule below still applies.

Video is the product. `/make <desk rank | story:ID>` builds a complete production package in
`outputs/videos/<id>/` (`research/video.py`, `scripts/make_video.py`): editorial angle, visual premise,
escalation and payoff, three hooks and a recommended one, full voiceover, scene-by-scene storyboard
with a Higgsfield prompt, duration, asset type, camera and motion direction and on-screen text per
shot, editing notes, sound direction, CTA, YouTube title and description, TikTok and Instagram
captions, and sources.

**The retention engine.** Everything after selection exists to turn the selected story into something
people watch to the end and send to a friend: "wait... WHAT?", "no way", "show me another one". It
never changes which story was selected and never re-runs discovery or ranking. The article provides
the information; `/make` finds the entertainment in it:

1. **Entertainment angle first**: the most surprising fact, the most entertaining consequence, the
   strongest visual, the relatable scenario, the "wait, what?" moment, why an ordinary viewer cares.
   Never the article's structure or headline.
2. **Money shot first**: the one visual that stops the scroll is shot 1.
3. **The first two seconds are sacred**: a consequence, question, shocking visual, mystery, reaction or
   challenge in a very short sentence. Never "Today we...", "According to...", a logo or background.
4. **One narrator** (`video.narrator`): our own original host who reacts instead of reporting, in plain
   spoken sentences. Never an imitation of an existing character, actor or real person.
5. **Curiosity and escalation**: hook, curiosity, small payoff, new question, bigger payoff, final
   payoff, next curiosity. Each beat beats the last.
6. **Every sentence has a visual; no dead attention.** Shots change when the story does.
7. **Captions are entertainment**: short punch captions on screen, the full transcript in `captions.srt`.
8. **Sound is part of the picture**: ambience, events and silence, never over the voice.
9. **Retention edit, then the scroll test**: cut everything the viewer does not need, do not protect the
   runtime, and answer the viewer-simulation questions honestly. A "no" means rework.
10. **End on the next curiosity**, never "follow for part two". Rotate hook styles; no two videos alike.

**Accuracy outranks all of it.** A voiceover line is `fact` (cites claims), `speculation` (must sound
conditional: could, might, imagine, if) or `framing`. The reaction can be dramatic; the claim cannot
mislead. Never make something sound confirmed because it makes a better hook. The checker
(`research/video.py → retention_issues`) enforces what can be enforced; the rest is judgement.

**Visual first.** Before scripting, answer "what should the viewer SEE?" and write the visual premise,
escalation and payoff. Not "GTA VI may have hurricanes" but "a hurricane could completely change a
police chase", then show the storm arriving, visibility dropping, streets flooding, the escape route
changing. The goal is original editorial visualisation that makes the narration understandable, never
fake gameplay. If no premise can be named, the story is not a short.

Rules (enforced by `make_video.py check`; errors block, warnings must be read):
- **Research is reused.** The video is written from the same evidence packet as the article. Every
  factual voiceover line cites a claim id; quotes are verbatim.
- **The video inherits the story's label.** Below `HIGH_CONFIDENCE_REPORT`, every hook and the title
  are hedged. "Confirmed" or "official" only when the label is `CONFIRMED`.
- **25-45 seconds, 9:16. Do not pad.** Hook in 0-2s, context to 8s, reveal and escalation to 25s,
  payoff to 35s, then a conclusion or a light CTA. Every scene moves the story forward.
- **Asset types:** `AI_VIDEO`, `AI_IMAGE_WITH_MOTION`, `TEXT_GRAPHIC`, `MAP_GRAPHIC`, `OTHER`, and the
  third-party types `SCREENSHOT`, `OFFICIAL_IMAGE`, `OFFICIAL_VIDEO_CLIP`. A third-party asset must be a
  source in the evidence packet (`asset_url`), carry a `rights_note`, and is flagged for the editor to
  clear before publishing. Original visuals are the default.
- **Generation prompts describe pictures, not articles:** subject, action, environment, composition,
  camera movement, motion, lighting, mood, style, duration, aspect ratio. One achievable action per
  3-6 second shot. They never name a game, studio or platform or ask for gameplay.
- **AI disclosure:** not on screen (operator decision, 5 Oct 2026). The full line goes in every
  description and caption ("AI-generated visualisation. Not actual <game> gameplay."), and the
  platform's own AI or altered-content setting is switched on at upload. Never present generated
  footage as real gameplay in the script, the title or a caption.
- **One visual system** (`config/design.yaml`, `research/design.py`): brand bug top left, a compact
  editorial tag top right (a source credit such as GAME INFORMER for a sourced fact, WHAT IF, NOT CONFIRMED), a hook title for under two seconds,
  captions in the lower area with one to three highlighted words, a short source line (quote and name
  only), and a two-line end card. The footage is the product: no full-screen cards, no boxes or
  outlines behind text, nothing in the centre of the frame, and never more than the moment needs.
  Per-video content goes in the package (`hook_title`, `end_card`, each shot's `graphics`, each
  voiceover line's `emphasis`); the look is changed only in the design config, for every video at once.
- **Not a voiced article, and not the last video again.** No "Did you know", slow intros, repeated
  headlines, unsupported hype, fake urgency or shots that do not match the narration. Choose the
  strongest treatment from `config/publishing.yaml → video.treatments`; do not default to BREAKING NEWS.

Statuses: `IDEA` → `SCRIPTED` → `READY_FOR_GENERATION` → `GENERATING` → `READY_FOR_REVIEW` → `APPROVED`
→ `PUBLISHED`, or `REJECTED`.

**`/render`** runs the whole production (`research/produce.py`, `make_video.py produce`): narration by
Higgsfield text-to-speech, one clip per voiceover line; shot lengths taken from the narration; a
continuity reference image, stills and clips generated through the installed `higgsfield` CLI; text
cards, tags, captions and the AI disclosure drawn locally from each shot's `on_screen_text`; assembly,
burned-in captions, voice, clip sound, ambience, music and loudness with FFmpeg; `final.mp4` written
into the package and the status set to `READY_FOR_REVIEW`. The editor only reviews the result. Text
graphics are never generated as AI video. The run is resumable and never pays twice for a finished
job. Models, voice, mix levels and fonts are in `config/publishing.yaml → video.production`.

The older paths remain as fallbacks (`research/higgsfield.py`, `make_video.py render`): it always shows the plan first: scenes, expected generations,
model per step, estimated cost (unknown prices are reported as unknown). Prefer 3-6 second scenes,
reuse of generated shots, image-to-video for near-static scenes and text graphics where generation
adds little. The default adapter is **manual**: it writes a sheet to follow in Higgsfield, and clips
saved into `assets/` are picked up by `ingest`. The **API adapter** follows docs.higgsfield.ai (submit,
persist the job id, poll, download, record model and cost, retry a failure safely, never resubmit a
moderated shot) and reads model paths, parameters and prices from config; never invent those.
**Paid generation requires the editor's explicit confirmation every time** (`--confirm`).

Nothing is uploaded or posted by any command. The editor posts; `/published` records it, which starts
the story's cooldown and opens its performance record.

## 15. Commercial, audience and data

- **Feature flags** (`config/flags.yaml`): ads, affiliate, newsletter, accounts, comments, reactions,
  auto-publish, auto video generation, auto social publishing. Only newsletter starts on.
- **Affiliate:** products live in `config/affiliates.yaml`, which starts empty. Never invent a
  product, price, merchant or affiliate link. Links carry `rel="sponsored nofollow noopener"` and a
  visible disclosure. `affiliate_enabled` goes on only when real, approved programmes exist.
  Commercial content must stay editorially credible; commercial score never outranks the facts.
- **The site currently has none of the following** (they live in `site-archive/`); these rules apply if
  any of it is restored.
- **Advertising:** positions are reserved (`AdSlot.astro`) and render nothing while `ads_enabled` is
  off. Do not enable ads until the site has real content and traffic.
- **Newsletter:** the form captures email, consent time, signup source, preferred games and topics.
  It submits only when `PUBLIC_NEWSLETTER_ENDPOINT` is set; until then it says sign-ups are not open.
  Never show a success message that is not true. No aggressive pop-ups.
- **Brand email:** addresses are built from `PUBLICATION_EMAIL_DOMAIN` (hello@, editorial@, tips@,
  partnerships@, privacy@). No personal address, and no credentials, anywhere in source.
- **Sponsorship:** never accept or imply a sponsorship on the operator's behalf. Editorial
  independence is not for sale; sponsored content would be labelled as such.
- **Video performance** (`scripts/perf.py`, tables `video_posts` and `video_metrics`): per post, the
  platform, publish time, views at 1h, 24h and 7d, likes, comments, shares, watch time, average
  percentage viewed, completion rate, follower gain, and the video's topic, game, treatment, hook
  style, length and visual style. The editor enters the numbers from each platform's analytics. This is
  a simple log, not an analytics platform.
- **Calibration** (table `story_ratings`): the operator's GREAT / GOOD / MEDIOCRE / BAD rating of a
  candidate, stored with the system's scores at that moment.
- **Analytics:** `site/public/ld.js` emits provider-independent events and sets no cookies. Report
  only numbers that were actually measured. Never estimate traffic, views, revenue or momentum.
