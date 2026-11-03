#!/usr/bin/env bash
# Build the production site (PUBLISHED articles only) with its real address and deploy it to Cloudflare.
# Run this after publishing: scripts/deploy_site.sh
# The address comes from config/publishing.yaml -> publication.site_url. Never deploys a preview build.
set -euo pipefail
cd "$(dirname "$0")/.."
SITE_URL="$(grep -E '^\s*site_url:' config/publishing.yaml | head -1 | sed -E 's/.*site_url:[[:space:]]*"?([^"#[:space:]]+)"?.*/\1/')"
case "$SITE_URL" in https://*) ;; *) echo "Set publication.site_url in config/publishing.yaml to the live https address first."; exit 1;; esac
[ -d "$HOME/.nvm/versions/node" ] && N="$(ls -d "$HOME"/.nvm/versions/node/v22* 2>/dev/null | sort -V | tail -1)" && [ -n "${N:-}" ] && export PATH="$N/bin:$PATH"
export SITE_URL
unset PREVIEW
cd site
npm run build
HOME_PAGE="dist/client/index.html"; [ -f "$HOME_PAGE" ] || HOME_PAGE="dist/index.html"
[ -f "$HOME_PAGE" ] || { echo "The build produced no home page. Not deploying."; exit 1; }
if grep -q "noindex" "$HOME_PAGE"; then echo "This build is marked noindex (a preview build). Not deploying."; exit 1; fi
npx wrangler deploy
echo "Deployed: $SITE_URL"
