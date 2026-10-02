#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HIVE_GATEWAY_ENV_FILE:-/etc/hive-agent-gateway/gateway.env}"
REPAIR=0
[[ "${1:-}" == "--repair" ]] && REPAIR=1

[[ -f "$ENV_FILE" ]] || { echo "GATEWAY_ENV=NOT_FOUND" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

HOST="${HIVE_AGENT_BRIDGE_HOST:-127.0.0.1}"
PORT="${HIVE_AGENT_BRIDGE_PORT:-9240}"
TOKEN="${HIVE_AGENT_BRIDGE_TOKEN:-}"
BASE="http://${HOST}:${PORT}"

(( ${#TOKEN} >= 32 )) || { echo "BRIDGE_TOKEN=INVALID_OR_MISSING" >&2; exit 3; }

local_probe(){
  local health agents protocol count
  health="$(curl -fsS --max-time 5 "${BASE}/health")" || return 1
  printf '%s' "$health" | jq -e '.ok == true and .protocol == "async-job-v1"' >/dev/null || return 1
  agents="$(curl -fsS --max-time 5 -H "Authorization: Bearer ${TOKEN}" "${BASE}/agents")" || return 1
  printf '%s' "$agents" | jq -e '.ok == true and (.agents | type == "array")' >/dev/null || return 1
  protocol="$(printf '%s' "$health" | jq -r '.protocol')"
  count="$(printf '%s' "$agents" | jq -r '.agents | length')"
  echo "LOCAL_HEALTH=PASS"
  echo "LOCAL_AUTH=PASS"
  echo "BRIDGE_PROTOCOL=${protocol}"
  echo "BRIDGE_REGISTERED_AGENT_SLOTS=${count}"
  return 0
}

if ! local_probe; then
  echo "LOCAL_HEALTH=FAIL" >&2
  if [[ "$REPAIR" == "1" ]]; then
    echo "WATCHDOG_RESTART=REQUESTED"
    systemctl restart hive-agent-gateway.service
    sleep 3
    local_probe || { echo "WATCHDOG_REPAIR=FAIL" >&2; exit 4; }
    echo "WATCHDOG_REPAIR=PASS"
  else
    exit 4
  fi
fi

PUBLIC_URL="${HIVE_AGENT_GATEWAY_PUBLIC_URL:-}"
if [[ -z "$PUBLIC_URL" ]]; then
  echo "PUBLIC_HEALTH=SKIPPED_NOT_CONFIGURED"
  exit 0
fi

CF_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"
if [[ -z "$CF_ID" || -z "$CF_SECRET" ]]; then
  echo "PUBLIC_HEALTH=SKIPPED_NO_CF_SERVICE_TOKEN"
  exit 0
fi

PUBLIC_URL="${PUBLIC_URL%/}"
public_health="$(curl -fsS --max-time 15 \
  -H "CF-Access-Client-Id: ${CF_ID}" \
  -H "CF-Access-Client-Secret: ${CF_SECRET}" \
  "${PUBLIC_URL}/health")" || { echo "PUBLIC_HEALTH=FAIL" >&2; exit 5; }
printf '%s' "$public_health" | jq -e '.ok == true and .protocol == "async-job-v1"' >/dev/null || { echo "PUBLIC_HEALTH=FAIL" >&2; exit 5; }

public_agents="$(curl -fsS --max-time 15 \
  -H "CF-Access-Client-Id: ${CF_ID}" \
  -H "CF-Access-Client-Secret: ${CF_SECRET}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${PUBLIC_URL}/agents")" || { echo "PUBLIC_AUTH=FAIL" >&2; exit 6; }
printf '%s' "$public_agents" | jq -e '.ok == true and (.agents | type == "array")' >/dev/null || { echo "PUBLIC_AUTH=FAIL" >&2; exit 6; }

echo "PUBLIC_HEALTH=PASS"
echo "PUBLIC_AUTH=PASS"
echo "SECRETS_EXPOSED=false"
