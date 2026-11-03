---
description: Re-check an article and mark it APPROVED. Approval is not deployment.
allowed-tools: Bash, Read
argument-hint: <article slug>
---

Approve the article: $ARGUMENTS

Only the Editor-in-Chief approves. Run this when the operator asks for it, never on your own initiative.
Use `.venv/bin/python` if `python` is not on PATH.

1. Read `site/src/content/articles/$ARGUMENTS.md` and its evidence packet in `data/evidence/`.
   Summarise for the editor: title, bucket, verification label, gate decision and reasons,
   unresolved conflicts, and any source that was cited without being opened.

2. Run `python scripts/approve_article.py $ARGUMENTS`. It:
   1. reruns the factual checks against the evidence packet
   2. validates required metadata and dates
   3. checks for duplicate content
   4. checks internal links and related_content
   5. builds the site (`npm run build` in `site/`)
   6. marks the article APPROVED only if every step passes

3. If any step fails, report exactly which one and why. Do not edit the article to make it pass
   unless the editor asks, and never use `--skip-build` unless the editor says the site toolchain is
   unavailable.

4. To reject instead: `python scripts/approve_article.py $ARGUMENTS --reject "<reason>"`.

APPROVED does not publish anything. Publishing is `python scripts/publish_article.py <slug>`, which
only changes the article's status so it appears in the next site build. Deployment to the public
internet is manual and stays off until the operator explicitly enables it in `config/publishing.yaml`.
