#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

WRANGLER=(npx --yes wrangler@latest)
CONFIG="$ROOT/wrangler.toml"
BOOTSTRAP="$ROOT/wrangler.bootstrap.toml"
TEMPLATE="$ROOT/wrangler.toml.template"
WHOAMI_OUT="/tmp/hive-kimi-cf-whoami.out"
WHOAMI_ERR="/tmp/hive-kimi-cf-whoami.err"

set +e
"${WRANGLER[@]}" whoami --config "$BOOTSTRAP" >"$WHOAMI_OUT" 2>"$WHOAMI_ERR"
WHOAMI_RC=$?
set -e
WHOAMI_TEXT="$(cat "$WHOAMI_OUT" "$WHOAMI_ERR" 2>/dev/null || true)"

if [[ "$WHOAMI_RC" -ne 0 ]] || printf '%s' "$WHOAMI_TEXT" | grep -Eqi 'not authenticated|please run.*wrangler login|login required'; then
  echo "CLOUDFLARE_LOGIN_REQUIRED"
  echo "Run this once in the Codespace:"
  echo "  npx --yes wrangler@latest login --device --browser=false"
  echo "Approve the device code in your browser, then rerun:"
  echo "  bash hive-kimi-cloudflare-worker/deploy.sh"
  exit 2
fi

printf '%s\n' "$WHOAMI_TEXT"

if [[ ! -f "$CONFIG" ]] || grep -q '__KV_NAMESPACE_ID__' "$CONFIG"; then
  echo "Creating dedicated Workers KV namespace for HIVE Kimi certification..."
  KV_OUT="$("${WRANGLER[@]}" kv namespace create HIVE_KIMI_RESULTS --config "$BOOTSTRAP" 2>&1 | tee /tmp/hive-kimi-cf-kv.log)"
  KV_ID="$(printf '%s\n' "$KV_OUT" | grep -Eo '[a-f0-9]{32}' | tail -n 1 || true)"
  if [[ -z "$KV_ID" ]]; then
    echo "Could not determine KV namespace ID." >&2
    cat /tmp/hive-kimi-cf-kv.log >&2 || true
    exit 1
  fi
  sed "s/__KV_NAMESPACE_ID__/${KV_ID}/g" "$TEMPLATE" > "$CONFIG"
  echo "KV namespace configured."
else
  echo "Using existing local Cloudflare KV binding."
fi

echo "Deploying stable HIVE Kimi Worker..."
DEPLOY_OUT="$("${WRANGLER[@]}" deploy --config "$CONFIG" 2>&1 | tee /tmp/hive-kimi-cf-deploy.log)"
PUBLIC_URL="$(printf '%s\n' "$DEPLOY_OUT" | grep -Eo 'https://[a-zA-Z0-9.-]+\.workers\.dev' | tail -n 1 || true)"

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Could not determine workers.dev URL from deployment output." >&2
  cat /tmp/hive-kimi-cf-deploy.log >&2 || true
  exit 1
fi

PUBLIC_OK=0
for _ in {1..20}; do
  if curl -fsS --max-time 10 "$PUBLIC_URL/health" >/tmp/hive-kimi-cf-health.json 2>/dev/null; then
    PUBLIC_OK=1
    break
  fi
  sleep 1
done

if [[ "$PUBLIC_OK" != "1" ]]; then
  echo "Worker deployed but public /health is not reachable yet." >&2
  echo "URL: $PUBLIC_URL" >&2
  exit 1
fi

curl -fsS --max-time 10 "$PUBLIC_URL/work" >/tmp/hive-kimi-cf-work.json

echo
echo "HIVE KIMI CLOUDFLARE WORKER READY"
echo "Base URL: $PUBLIC_URL"
echo "Health: $PUBLIC_URL/health"
echo "Work URL: $PUBLIC_URL/work"
echo "Work Result URL: $PUBLIC_URL/work-result"
echo
echo "This is a stable workers.dev endpoint, not a Quick Tunnel."
