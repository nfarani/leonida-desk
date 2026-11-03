import { getCollection, type CollectionEntry } from 'astro:content';
import type { Bucket } from '../config';

export type Article = CollectionEntry<'articles'>;

// A production build shows PUBLISHED articles only. PREVIEW=1 (npm run preview:drafts) also shows
// drafts and articles awaiting review so the editor can read them; those pages are marked noindex.
export const PREVIEW = process.env.PREVIEW === '1';

export function isVisible(a: Article): boolean {
  if (a.data.status === 'PUBLISHED') return true;
  return PREVIEW && a.data.status !== 'REJECTED';
}

export function sortDate(a: Article): Date {
  return a.data.published_at ?? a.data.updated_at ?? new Date(0);
}

export async function visibleArticles(bucket?: Bucket, section?: 'gaming' | 'tech'): Promise<Article[]> {
  const all = await getCollection('articles', isVisible);
  return all
    .filter((a) => !bucket || a.data.editorial_bucket === bucket)
    .filter((a) => !section || a.data.section === section)
    .sort((a, b) => sortDate(b).getTime() - sortDate(a).getTime());
}

/** Only articles that are really published: used for the sitemap, the feed and structured data. */
export async function publishedArticles(): Promise<Article[]> {
  const all = await getCollection('articles', (a) => a.data.status === 'PUBLISHED');
  return all.sort((a, b) => sortDate(b).getTime() - sortDate(a).getTime());
}

/** Explicit related_content first, then same-bucket and shared-tag articles. Never invents links. */
export function related(article: Article, all: Article[], limit = 3): Article[] {
  const others = all.filter((a) => a.data.slug !== article.data.slug);
  const picked = article.data.related_content
    .map((slug) => others.find((a) => a.data.slug === slug))
    .filter((a): a is Article => Boolean(a));
  const scored = others
    .filter((a) => !picked.includes(a))
    .map((a) => ({
      a,
      score: a.data.tags.filter((t) => article.data.tags.includes(t)).length * 2 + (a.data.editorial_bucket === article.data.editorial_bucket ? 1 : 0),
    }))
    .filter((x) => x.score > 0)
    .sort((x, y) => y.score - x.score)
    .map((x) => x.a);
  return [...picked, ...scored].slice(0, limit);
}

export function fmtDate(d: Date | null | undefined): string {
  if (!d) return 'Not yet published';
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}
