#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

WRANGLER=(npx --yes wrangler@latest)
CONFIG="$ROOT/wrangler.toml"
BOOTSTRAP="$ROOT/wrangler.bootstrap.toml"
TEMPLATE="$ROOT/wrangler.toml.template"
WHOAMI_LOG="/tmp/hive-kimi-cf-whoami.log"
KV_LOG="/tmp/hive-kimi-cf-kv.log"
DEPLOY_LOG="/tmp/hive-kimi-cf-deploy.log"
HEALTH_BODY="/tmp/hive-kimi-cf-health.body"
HEALTH_HEADERS="/tmp/hive-kimi-cf-health.headers"

# Wrangler v4 can print "not authenticated" while still exiting 0, so inspect output too.
set +e
"${WRANGLER[@]}" whoami --config "$BOOTSTRAP" >"$WHOAMI_LOG" 2>&1
WHOAMI_STATUS=$?
set -e
cat "$WHOAMI_LOG"

if [[ "$WHOAMI_STATUS" -ne 0 ]] || grep -qiE 'not authenticated|please run .*wrangler login|login required' "$WHOAMI_LOG"; then
  echo
  echo "CLOUDFLARE_LOGIN_REQUIRED"
  echo "Run this once in the Codespace:"
  echo "  npx --yes wrangler@latest login --device --browser=false"
  echo "Approve the device code in your browser, then rerun:"
  echo "  bash hive-kimi-cloudflare-worker/deploy.sh"
  exit 2
fi

if [[ ! -f "$CONFIG" ]] || grep -q '__KV_NAMESPACE_ID__' "$CONFIG"; then
  echo "Creating dedicated Workers KV namespace for HIVE Kimi certification..."
  : >"$KV_LOG"
  set +e
  "${WRANGLER[@]}" kv namespace create HIVE_KIMI_RESULTS --config "$BOOTSTRAP" >"$KV_LOG" 2>&1
  KV_STATUS=$?
  set -e
  cat "$KV_LOG"

  if [[ "$KV_STATUS" -ne 0 ]]; then
    echo
    echo "CLOUDFLARE_KV_CREATE_FAILED"
    echo "The exact Wrangler error is shown above."
    echo "No Worker deployment was attempted."
    exit "$KV_STATUS"
  fi

  KV_ID="$(grep -Eo '[a-f0-9]{32}' "$KV_LOG" | tail -n 1 || true)"
  if [[ -z "$KV_ID" ]]; then
    echo "Could not determine KV namespace ID from Wrangler output." >&2
    exit 1
  fi

  sed "s/__KV_NAMESPACE_ID__/${KV_ID}/g" "$TEMPLATE" > "$CONFIG"
  echo "KV namespace configured: ${KV_ID}"
else
  echo "Using existing local Cloudflare KV binding."
fi

echo "Deploying stable HIVE Kimi Worker..."
: >"$DEPLOY_LOG"
set +e
"${WRANGLER[@]}" deploy --config "$CONFIG" >"$DEPLOY_LOG" 2>&1
DEPLOY_STATUS=$?
set -e
cat "$DEPLOY_LOG"

if [[ "$DEPLOY_STATUS" -ne 0 ]]; then
  echo
  echo "CLOUDFLARE_WORKER_DEPLOY_FAILED"
  exit "$DEPLOY_STATUS"
fi

PUBLIC_URL="$(grep -Eo 'https://[a-zA-Z0-9.-]+\.workers\.dev' "$DEPLOY_LOG" | tail -n 1 || true)"

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Could not determine workers.dev URL from deployment output." >&2
  exit 1
fi

PUBLIC_OK=0
for _ in {1..20}; do
  : >"$HEALTH_BODY"
  : >"$HEALTH_HEADERS"
  set +e
  curl -sS --max-time 10 -D "$HEALTH_HEADERS" -o "$HEALTH_BODY" "$PUBLIC_URL/health"
  CURL_STATUS=$?
  set -e
  HTTP_STATUS="$(awk 'toupper($1) ~ /^HTTP\// {code=$2} END {print code}' "$HEALTH_HEADERS")"
  if [[ "$CURL_STATUS" -eq 0 && "$HTTP_STATUS" == "200" ]]; then
    PUBLIC_OK=1
    break
  fi
  sleep 1
done

if [[ "$PUBLIC_OK" != "1" ]]; then
  echo
  echo "CLOUDFLARE_WORKER_HEALTH_FAILED"
  echo "URL: $PUBLIC_URL/health"
  echo "curl_status: ${CURL_STATUS:-unknown}"
  echo "http_status: ${HTTP_STATUS:-unknown}"
  echo "--- response headers ---"
  cat "$HEALTH_HEADERS" || true
  echo "--- response body ---"
  cat "$HEALTH_BODY" || true
  echo
  echo "Worker deployment succeeded, but public execution failed."
  exit 1
fi

set +e
curl -sS --max-time 10 -D /tmp/hive-kimi-cf-work.headers -o /tmp/hive-kimi-cf-work.json "$PUBLIC_URL/work"
WORK_CURL_STATUS=$?
set -e
WORK_HTTP_STATUS="$(awk 'toupper($1) ~ /^HTTP\// {code=$2} END {print code}' /tmp/hive-kimi-cf-work.headers)"
if [[ "$WORK_CURL_STATUS" -ne 0 || "$WORK_HTTP_STATUS" != "200" ]]; then
  echo
  echo "CLOUDFLARE_WORKER_WORK_FAILED"
  echo "http_status: ${WORK_HTTP_STATUS:-unknown}"
  cat /tmp/hive-kimi-cf-work.json || true
  exit 1
fi

echo
echo "HIVE KIMI CLOUDFLARE WORKER READY"
echo "Base URL: $PUBLIC_URL"
echo "Health: $PUBLIC_URL/health"
echo "Work URL: $PUBLIC_URL/work"
echo "Work Result URL: $PUBLIC_URL/work-result"
echo
echo "This is a stable workers.dev endpoint, not a Quick Tunnel."
