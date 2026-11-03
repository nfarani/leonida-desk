// Publication identity and switches for the site build.
// Flags, games and affiliate products are read from ../config/*.yaml so the pipeline and the site
// share one source of truth. Addresses and endpoints come from the environment, never from source.
import fs from 'node:fs';
import path from 'node:path';
import { load as loadYaml } from 'js-yaml';

const root = path.resolve(process.cwd(), '..', 'config');
const read = (name: string): any => loadYaml(fs.readFileSync(path.join(root, name), 'utf8'));

export const SITE = {
  name: 'Leonida Desk',
  tagline: 'Gaming news, discoveries and explainers, with the sources shown.',
  description:
    'Leonida Desk is an independent gaming publication. Every factual claim is traced to a source and carries a verification label.',
  byline: 'Leonida Desk',
  locale: 'en-GB',
};

export const FLAGS: Record<string, boolean> = read('flags.yaml').flags;

export interface Game {
  slug: string; name: string; short_name?: string; franchise?: string | null; flagship?: boolean; path?: string;
  developer?: string | null; publisher?: string | null; platforms?: string[] | null;
  release_date?: string | null; release_date_label?: string; summary?: string | null; sources?: string[];
}
export const GAMES: Game[] = Object.entries(read('games.yaml').games as Record<string, any>).map(([slug, g]) => ({ slug, ...g }));
export const gamePath = (g: Game) => g.path ?? `/games/${g.slug}/`;
export const findGame = (slug?: string | null) => GAMES.find((g) => g.slug === slug);

const aff = read('affiliates.yaml');
export const AFFILIATE = {
  enabled: Boolean(FLAGS.affiliate_enabled),
  disclosure: aff.disclosure as string,
  products: (aff.products ?? {}) as Record<string, any>,
};

// Brand email. Set PUBLICATION_EMAIL_DOMAIN (e.g. leonidadesk.com) at build time. Until it is set
// no address is shown anywhere: we never publish a personal or placeholder address.
const domain = process.env.PUBLICATION_EMAIL_DOMAIN || '';
const address = (local: string) => (domain ? `${local}@${domain}` : null);
export const EMAIL = {
  domain,
  hello: address('hello'), editorial: address('editorial'), tips: address('tips'),
  partnerships: address('partnerships'), privacy: address('privacy'),
};

// Provider-independent endpoints. Empty means "not connected": forms say so instead of pretending.
export const ENDPOINTS = {
  newsletter: process.env.PUBLIC_NEWSLETTER_ENDPOINT || '',
  analytics: process.env.PUBLIC_ANALYTICS_ENDPOINT || '',
  contact: process.env.PUBLIC_CONTACT_ENDPOINT || '',
};

export const AD_SLOTS = ['homepage-feed', 'article-top', 'article-middle', 'article-bottom', 'sidebar', 'related'] as const;

export const NAV: [string, string][] = [
  ['Latest', '/latest/'], ['GTA VI', '/gta-vi/'], ['News', '/news/'], ['Discoveries', '/discoveries/'],
  ['Explainers', '/explainers/'], ['Guides', '/guides/'], ['Reviews', '/reviews/'], ['Videos', '/videos/'],
  ['Newsletter', '/newsletter/'], ['About', '/about/'],
];

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
