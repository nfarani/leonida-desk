import { defineConfig } from 'astro/config';

// SITE_URL must be the real domain before any deployment: canonical URLs, the sitemap and the RSS
// feed are all built from it.
export default defineConfig({
  site: process.env.SITE_URL || 'http://localhost:4321',
  trailingSlash: 'always',
  build: { format: 'directory' },
});
