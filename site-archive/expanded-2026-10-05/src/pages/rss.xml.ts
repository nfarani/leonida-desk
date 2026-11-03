import type { APIRoute } from 'astro';
import { SITE } from '../config';
import { publishedArticles } from '../lib/articles';

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export const GET: APIRoute = async ({ site }) => {
  const items = (await publishedArticles()).slice(0, 50).map((a) => {
    const url = new URL(`/articles/${a.data.slug}/`, site).href;
    return `<item><title>${esc(a.data.title)}</title><link>${url}</link><guid isPermaLink="true">${url}</guid>` +
      `<description>${esc(a.data.description)}</description><pubDate>${a.data.published_at!.toUTCString()}</pubDate></item>`;
  });
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>${esc(SITE.name)}</title>` +
    `<link>${site?.href}</link><description>${esc(SITE.description)}</description><language>${SITE.locale}</language>${items.join('')}</channel></rss>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
};
