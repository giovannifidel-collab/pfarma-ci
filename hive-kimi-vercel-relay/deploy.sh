#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERCEL=(npx --yes vercel@latest)

if ! "${VERCEL[@]}" whoami >/tmp/hive-kimi-vercel-whoami.out 2>/tmp/hive-kimi-vercel-whoami.err; then
  echo "VERCEL_LOGIN_REQUIRED"
  echo "Run this once, complete the browser/device login, then rerun deploy.sh:"
  echo "  npx --yes vercel@latest login"
  exit 2
fi

WHOAMI="$(cat /tmp/hive-kimi-vercel-whoami.out | tail -n 1)"
echo "Vercel authenticated as: ${WHOAMI}"

echo "Deploying isolated HIVE Kimi relay..."
DEPLOY_OUT="$("${VERCEL[@]}" --prod --yes --scope project-giovanni 2>&1 | tee /tmp/hive-kimi-vercel-deploy.log)"

PUBLIC_URL="$(printf '%s\n' "$DEPLOY_OUT" | grep -Eo 'https://[a-zA-Z0-9.-]+\.vercel\.app' | tail -n 1 || true)"
if [[ -z "$PUBLIC_URL" ]]; then
  echo "Could not determine Vercel URL. Full deploy output:" >&2
  cat /tmp/hive-kimi-vercel-deploy.log >&2
  exit 1
fi

for _ in {1..20}; do
  if curl -fsS --max-time 10 "$PUBLIC_URL/api/work" >/tmp/hive-kimi-vercel-work.json 2>/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -fsS --max-time 10 "$PUBLIC_URL/api/work" >/tmp/hive-kimi-vercel-work.json; then
  echo "Deployment exists but /api/work is not publicly reachable." >&2
  echo "URL: $PUBLIC_URL" >&2
  exit 1
fi

echo
echo "HIVE KIMI VERCEL RELAY READY"
echo "Base URL: $PUBLIC_URL"
echo "Work URL: $PUBLIC_URL/api/work"
echo "Callback base: $PUBLIC_URL/api/work-submit"
echo
echo "The endpoint is standalone and contains no production data or AI API keys."
