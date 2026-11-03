---
story_id: 1660
parent_event_id: null
angle_id: cloudflare-deno
hero_media: null
related_content: []
status: REVIEW_REQUIRED
title: 'Cloudflare is buying Deno: what was announced and what was left out'
slug: cloudflare-acquires-deno
description: Cloudflare is acquiring the company behind the Deno runtime to build up Workers. The stated reasons, the people involved, and the questions not yet answered.
editorial_bucket: BREAKING
verification_status: CREDIBLE_RUMOUR
game: null
content_type: news
section: tech
tags:
- Cloudflare
- Deno
- software
- developers
article_id: cloudflare-acquires-deno
author: Leonida Desk
created_at: '2026-10-11T19:20:49+00:00'
published_at: null
updated_at: '2026-10-11T19:20:49+00:00'
content_hash: 9ccf471928a24b1a
sources:
- name: TechCrunch
  url: https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model
  title: Cloudflare acquires Deno to improve its Workers programming model
  published_at: '2026-10-10T16:25:42+00:00'
evidence_packet: story-1660-cloudflare-deno
originality_score: 69
quality_score: 95
gate: REVIEW_REQUIRED
gate_reasons:
- credible rumour always needs an editor
- originality 69 is below 70
- needs 2 independent credible sources or a primary source (has 1 credible, 0 primary)
---

Cloudflare is acquiring Deno, the startup behind the programming runtime of the same name.[^c2]

*This site is hosted on Cloudflare Workers, the product this deal concerns. We have no other relationship with either company. This article rests on one report, from TechCrunch.*

## What was announced

| Question | Answer |
|---|---|
| Who is buying whom? | Cloudflare is acquiring Deno[^c2] |
| When was it announced? | Friday[^c2] |
| Why? | To improve the Workers programming model and platform[^c3] |
| Price | Not disclosed[^c8] |
| Deno's funding to date | $26 million, including a Series A led by Sequoia[^c8] |

Workers is the Cloudflare service that lets customers build and run software on the company's network.[^c3] Deno was co-founded by Bert Belder and Ryan Dahl, who also created Node.js.[^c4]

## What each side said

Dahl described the move as "joining Cloudflare to make the Workers programming model a mainstream way to build servers".[^c7]

For Cloudflare, Kenton Varda, the principal engineer for Workers, tied the deal to a project Deno had already shipped: celld, an open source implementation of Workers.[^c5] He also used the moment to push back on the idea that Workers was built differently in order to trap customers, arguing that "being open source and giving people an escape hatch is good business".[^c6]

## Our read

The order of events is the interesting part. Deno built an open source version of Cloudflare's own model first, and the acquisition followed.[^c5][^c2] That makes this look less like a company buying a rival runtime and more like one hiring the people who had just shown they could reimplement its platform in the open.[^c3]

The lock-in remark matters for the same reason. A platform that wants its way of writing servers to become a standard needs developers to believe they could leave, and an open implementation is the evidence for that.[^c6]

## What we don't know

The report does not say what happens to the Deno runtime itself, to Deno's existing hosting customers, or to celld's licence and governance after the deal closes.[^c2] The price is undisclosed, and no closing date is given.[^c8]

<!-- citations:start -->
[^c2]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
[^c3]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
[^c8]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
[^c4]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
[^c7]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
[^c5]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
[^c6]: [TechCrunch: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model), 2026-10-10.
<!-- citations:end -->
