#!/usr/bin/env bash
# ─── Open Gojira Website — Deploy to Cloudflare Pages ───────────────────────
set -euo pipefail

cd "$(dirname "$0")"

echo "🔨 Building production bundle..."
npm run build

echo "🚀 Deploying to Cloudflare Pages..."
CLOUDFLARE_LOG_FILE=/tmp/wrangler.log npx wrangler pages deploy dist \
  --project-name open-gojira \
  --branch master \
  --commit-dirty=true

echo ""
echo "✅ Deployed! Permanent URL: https://open-gojira.pages.dev"
