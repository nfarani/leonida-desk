import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const date = z.preprocess((v) => (v === null || v === undefined || v === '' ? null : new Date(v as string)), z.date().nullable());

// Mirrors the article front matter written by research/articles.py.
const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/articles' }),
  schema: z.object({
    article_id: z.string(),
    story_id: z.number().nullable().optional(),
    parent_event_id: z.number().nullable().optional(),
    angle_id: z.string().nullable().optional(),
    title: z.string(),
    slug: z.string(),
    description: z.string(),
    hero_media: z.object({ src: z.string(), alt: z.string(), credit: z.string().optional() }).nullable().optional(),
    author: z.string(),
    published_at: date,
    updated_at: date,
    editorial_bucket: z.enum(['BREAKING', 'DISCOVERY', 'EXPLAINER', 'EVERGREEN']),
    verification_status: z.enum(['CONFIRMED', 'HIGH_CONFIDENCE_REPORT', 'CREDIBLE_RUMOUR', 'COMMUNITY_DISCOVERY', 'THEORY', 'SPECULATION', 'FALSE_OR_DEBUNKED']),
    tags: z.array(z.string()).default([]),
    sources: z.array(z.object({ name: z.string(), url: z.string().url(), title: z.string().optional(), published_at: z.string().nullable().optional() })).default([]),
    related_content: z.array(z.string()).default([]),
    game: z.string().nullable().optional(),            // slug in config/games.yaml
    content_type: z.enum(['news', 'discovery', 'explainer', 'guide', 'review', 'commercial']).optional(),
    affiliate_products: z.array(z.string()).default([]), // ids in config/affiliates.yaml
    video_id: z.string().nullable().optional(),
    status: z.enum(['DRAFT', 'REVIEW_REQUIRED', 'APPROVED', 'PUBLISHED', 'REJECTED']),
    originality_score: z.number().optional(),
    quality_score: z.number().optional(),
    gate: z.string().optional(),
    gate_reasons: z.array(z.string()).optional(),
    evidence_packet: z.string().optional(),
  }).passthrough(),
});

export const collections = { articles };
