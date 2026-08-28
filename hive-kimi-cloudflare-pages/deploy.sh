#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PROJECT="hive-kimi-relay-pages"
DIST="$ROOT/dist"
WRANGLER=(npx --yes wrangler@latest)
ACCOUNT_ID="6f6de52331e398c395d3de97c83011cd"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"
CREATE_LOG="/tmp/hive-kimi-pages-create.log"
DEPLOY_LOG="/tmp/hive-kimi-pages-deploy.log"
HEALTH_BODY="/tmp/hive-kimi-pages-health.body"
HEALTH_HEADERS="/tmp/hive-kimi-pages-health.headers"

echo "Cloudflare account pinned for Pages: $CLOUDFLARE_ACCOUNT_ID"
"${WRANGLER[@]}" whoami

# Idempotent project setup: attempt creation every time and tolerate the
# documented 'already exists' response. This avoids relying on Pages project
# list output/JSON behavior, which varies across Wrangler versions.
echo "Ensuring Cloudflare Pages project exists: $PROJECT"
set +e
"${WRANGLER[@]}" pages project create "$PROJECT" --production-branch main >"$CREATE_LOG" 2>&1
CREATE_STATUS=$?
set -e
cat "$CREATE_LOG"
if [[ "$CREATE_STATUS" -ne 0 ]] && ! grep -qiE 'already exists|already been taken|code:[[:space:]]*8000002' "$CREATE_LOG"; then
  echo "CLOUDFLARE_PAGES_PROJECT_CREATE_FAILED" >&2
  exit "$CREATE_STATUS"
fi
if [[ "$CREATE_STATUS" -ne 0 ]]; then
  echo "Using existing Cloudflare Pages project: $PROJECT"
fi

# Pages rejects custom config paths. We run from the project directory and let
# Wrangler discover ./wrangler.toml automatically. account selection comes from
# CLOUDFLARE_ACCOUNT_ID, not from wrangler.toml (Pages does not support account_id there).
echo "Deploying HIVE Kimi relay to Cloudflare Pages..."
set +e
"${WRANGLER[@]}" pages deploy "$DIST" --project-name "$PROJECT" --branch main >"$DEPLOY_LOG" 2>&1
DEPLOY_STATUS=$?
set -e
cat "$DEPLOY_LOG"
if [[ "$DEPLOY_STATUS" -ne 0 ]]; then
  echo "CLOUDFLARE_PAGES_DEPLOY_FAILED" >&2
  exit "$DEPLOY_STATUS"
fi

PUBLIC_URL="https://${PROJECT}.pages.dev"
PUBLIC_OK=0
for _ in {1..30}; do
  STATUS="$(curl -sS --max-time 10 -D "$HEALTH_HEADERS" -o "$HEALTH_BODY" -w '%{http_code}' "$PUBLIC_URL/health" || true)"
  if [[ "$STATUS" == "200" ]] && grep -q '"ok"[[:space:]]*:[[:space:]]*true' "$HEALTH_BODY"; then
    PUBLIC_OK=1
    break
  fi
  sleep 1
done

if [[ "$PUBLIC_OK" != "1" ]]; then
  echo
  echo "CLOUDFLARE_PAGES_HEALTH_FAILED"
  echo "URL: $PUBLIC_URL/health"
  echo "--- response headers ---"
  cat "$HEALTH_HEADERS" 2>/dev/null || true
  echo "--- response body ---"
  cat "$HEALTH_BODY" 2>/dev/null || true
  exit 1
fi

curl -fsS --max-time 10 "$PUBLIC_URL/work" >/tmp/hive-kimi-pages-work.json

echo
echo "HIVE KIMI CLOUDFLARE PAGES READY"
echo "Base URL: $PUBLIC_URL"
echo "Health: $PUBLIC_URL/health"
echo "Work URL: $PUBLIC_URL/work"
echo "Work Result URL: $PUBLIC_URL/work-result"
echo
echo "Cloudflare Pages is being used only as the public front door; the relay remains on Cloudflare and uses the existing HIVE Kimi KV namespace."
