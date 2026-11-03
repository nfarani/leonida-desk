import { defineConfig } from 'astro/config';

import cloudflare from '@astrojs/cloudflare';

// SITE_URL must be the real domain before any deployment: canonical URLs, the sitemap and the RSS
// feed are all built from it.
export default defineConfig({
  site: process.env.SITE_URL || 'http://localhost:4321',
  trailingSlash: 'always',
  build: { format: 'directory' },
  adapter: cloudflare(),
  // The Cloudflare adapter renders pages outside Node, where process.env is not the shell's. PREVIEW
  // (npm run preview:drafts) is therefore fixed at config time.
  vite: { define: { 'process.env.PREVIEW': JSON.stringify(process.env.PREVIEW || '') } },
});