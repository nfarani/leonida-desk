---
description: Draft an article from a recommendation or story, evidence first. Never publishes.
allowed-tools: Bash, Read, Write, Edit, WebFetch
argument-hint: <recommendation rank | story:ID | topic:ID>
---

Draft one article for: $ARGUMENTS

Follow CLAUDE.md strictly, in particular section 13 (Content desk). You are writing for a publication
whose rule is: every factual claim traces to a stored source that was opened in this session.
Use `.venv/bin/python` if `python` is not on PATH.

1. **Retrieve the story.** `python scripts/article.py packet $ARGUMENTS`
   (add `--also <story ids>` when several stored stories are the same event, and `--angle-id <slug>`
   plus `--angle "<one line>"` once you know the angle). This writes an evidence packet to
   `data/evidence/` and lists the stored sources with ids (s1, s2, ...).

2. **Fetch and recheck the sources.** Open every source you intend to cite. If a page is blocked, try
   once more with curl and a browser user agent; if it still fails, do not cite it. Mark what you
   opened: `python scripts/article.py opened <packet> s1 s4 ...`. Only stored sources may be cited.
   Never add a URL from memory.

3. **Build the evidence packet.** For each fact you plan to state, add a claim:
   `python scripts/article.py claim <packet> --source s4 --claim "..." --evidence "<paraphrase of what the page says>" [--quote "<verbatim text>"]`
   A quote must be word for word from the page. Seed claims marked `headline` are not evidence.
   If sources disagree, record it: `python scripts/article.py conflict <packet> "<what differs>"`.

4. **Decide the angle.** State in one line what this article adds that its sources do not: synthesis
   across sources, comparison with earlier Rockstar games, context, a timeline, a fact check, a
   structured reference. Any comparison or history must itself be in the evidence packet.

5. **Decide whether there is enough substance.** If you have fewer than three verified claims, or the
   only possible article is a paraphrase of one outlet, stop and tell the editor it should be
   VIDEO_ONLY or IGNORE. Do not write a thin article because the command was called.

6. **Draft.** Write `site/src/content/articles/<slug>.md` with front matter (story_id, parent_event_id,
   angle_id, title, slug, description, hero_media: null, author: the publication byline,
   editorial_bucket, verification_status, tags, related_content, status: DRAFT, evidence_packet).
   - Every paragraph that states a fact ends with its citations, written `[^c12]` using claim ids.
   - Put interpretation under a heading such as "Why it matters", "How it compares", "Context" or
     "What we don't know". Analysis must not introduce numbers, quotes or attributions.
   - `verification_status` must not exceed the packet's `story_label`. Never write "confirmed" or
     "official" in a title or description unless the label is CONFIRMED.
   - No hero image unless its rights are clear. No invented author.
   - Write for the reader: lead with what happened, no padding, no target word count.

7. **Score, fact-check and gate.** `python scripts/article.py check <slug>`
   This recomputes originality and quality, checks every citation and quote against the packet, looks
   for duplicates and broken links, regenerates the footnotes, and sets the status.

8. **Fix what it flags.** Every `ERROR` line is an unsupported claim, an unverifiable quote or missing
   information. Fix the draft (or remove the claim) and run step 7 again. Do not weaken the checks.

9. **Report to the editor:** the angle, the label, originality and quality, the gate decision and its
   reasons, any unresolved conflicts, and which sources you could not open.

The article ends as DRAFT (blocked by the gate) or REVIEW_REQUIRED. It is not approved, not published
and not deployed. Approval is a separate command: `/approve-article <slug>`.
