import type { APIRoute } from 'astro';
import { publishedArticles } from '../lib/articles';

const PAGES = ['/', '/latest/', '/news/', '/discoveries/', '/explainers/', '/guides/', '/tech/', '/about/', '/editorial-standards/', '/ai-disclosure/'];

// Only published articles, with their real last-modified dates.
export const GET: APIRoute = async ({ site }) => {
  const urls = PAGES.map((p) => `<url><loc>${new URL(p, site).href}</loc></url>`);
  for (const a of await publishedArticles()) {
    const mod = (a.data.updated_at ?? a.data.published_at)!.toISOString();
    urls.push(`<url><loc>${new URL(`/articles/${a.data.slug}/`, site).href}</loc><lastmod>${mod}</lastmod></url>`);
  }
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join('')}</urlset>`,
    { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
