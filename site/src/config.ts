// Publication identity. Keep in step with config/publishing.yaml -> publication.
export const SITE = {
  name: 'Leonida Desk',
  tagline: 'Gaming and tech news, discoveries and explainers, with the sources shown.',
  description:
    'An independent gaming news blog with a close focus on Grand Theft Auto VI, plus product news from the wider world of gadgets and software. Every factual claim is traced to a source and carries a verification label.',
  byline: 'Leonida Desk',
  locale: 'en-GB',
};

export const BUCKETS = {
  BREAKING: { label: 'News', path: '/news/', blurb: 'New developments, labelled by how well they are sourced.' },
  DISCOVERY: { label: 'Discoveries', path: '/discoveries/', blurb: 'Details found in official material. What is observed, and what is interpretation.' },
  EXPLAINER: { label: 'Explainers', path: '/explainers/', blurb: 'What a development means, how it compares, and what is still unknown.' },
  EVERGREEN: { label: 'Guides', path: '/guides/', blurb: 'Reference pieces that stay useful: what is on the record, kept up to date.' },
} as const;

export type Bucket = keyof typeof BUCKETS;

export const LABELS: Record<string, { text: string; tone: string; meaning: string }> = {
  CONFIRMED: { text: 'Confirmed', tone: 'confirmed', meaning: 'Stated by the developer, publisher or platform holder in an official channel.' },
  HIGH_CONFIDENCE_REPORT: { text: 'High-confidence report', tone: 'report', meaning: 'Reported by a top-tier outlet. Not an official statement.' },
  CREDIBLE_RUMOUR: { text: 'Credible rumour', tone: 'rumour', meaning: 'Unconfirmed, but carried by credible journalism.' },
  COMMUNITY_DISCOVERY: { text: 'Community discovery', tone: 'discovery', meaning: 'An observable find in official material. The interpretation is unverified.' },
  THEORY: { text: 'Theory', tone: 'theory', meaning: 'A reasoned interpretation by the community. Not fact.' },
  SPECULATION: { text: 'Speculation', tone: 'speculation', meaning: 'Unsourced or weakly sourced.' },
  FALSE_OR_DEBUNKED: { text: 'False / debunked', tone: 'debunked', meaning: 'Officially denied or credibly disproven.' },
};
