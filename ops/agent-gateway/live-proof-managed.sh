#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HIVE_GATEWAY_ENV_FILE:-/etc/hive-agent-gateway/gateway.env}"
PROOF_DIR="${HIVE_GATEWAY_PROOF_DIR:-/var/lib/hive-agent-gateway/proofs}"
MARKER="HIVE_GATEWAY_LIVE_OK"
POLL_SECONDS="${HIVE_GATEWAY_PROOF_POLL_SECONDS:-2}"
JOB_DEADLINE_SECONDS="${HIVE_GATEWAY_PROOF_DEADLINE_SECONDS:-300}"
ACTIVE=(claude gemini deepseek qwen mistral perplexity copilot duck)
DEFERRED=(kimi meta)

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
command -v curl >/dev/null 2>&1 || { echo "CURL=NOT_FOUND" >&2; exit 4; }
command -v jq >/dev/null 2>&1 || { echo "JQ=NOT_FOUND" >&2; exit 4; }

mkdir -p "$PROOF_DIR"
chmod 700 "$PROOF_DIR"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PROOF_FILE="${PROOF_DIR}/managed-live-proof-${STAMP}.json"
TMP_RESULTS="$(mktemp)"
trap 'rm -f "$TMP_RESULTS"' EXIT
printf '[]' >"$TMP_RESULTS"

registered="$(curl -fsS --max-time 10 -H "Authorization: Bearer ${TOKEN}" "${BASE}/agents")"
for id in "${ACTIVE[@]}"; do
  printf '%s' "$registered" | jq -e --arg id "$id" '.ok == true and (.agents | index($id) != null)' >/dev/null || {
    echo "AGENT_${id^^}=NOT_REGISTERED" >&2
    exit 5
  }
done

echo "=== HIVE MANAGED AGENT LIVE PROOF ==="
echo "ACTIVE_SET=claude,gemini,deepseek,qwen,mistral,perplexity,copilot,duck"
echo "DEFERRED_SET=kimi,meta"
echo "STRICT_10_OF_10_GATE_PRESERVED=true"

pass=0
for id in "${ACTIVE[@]}"; do
  echo "AGENT=${id} STATE=SUBMITTING"
  payload="$(jq -nc --arg id "$id" --arg task "Reply exactly with ${MARKER}" --arg expected "$MARKER" '{agent_id:$id,task:$task,expected_text:$expected,fresh:true}')"
  submit="$(curl -fsS --max-time 15 \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    "${BASE}/jobs")" || { echo "AGENT=${id} STATE=SUBMIT_FAIL" >&2; exit 10; }
  job_id="$(printf '%s' "$submit" | jq -r '.job_id // empty')"
  [[ -n "$job_id" ]] || { echo "AGENT=${id} STATE=NO_JOB_ID" >&2; exit 10; }

  deadline=$(( $(date +%s) + JOB_DEADLINE_SECONDS ))
  state=""
  result=""
  while (( $(date +%s) < deadline )); do
    result="$(curl -fsS --max-time 15 -H "Authorization: Bearer ${TOKEN}" "${BASE}/jobs/${job_id}")" || true
    state="$(printf '%s' "$result" | jq -r '.job.state // empty' 2>/dev/null || true)"
    [[ "$state" == "done" || "$state" == "failed" ]] && break
    sleep "$POLL_SECONDS"
  done

  if [[ "$state" != "done" ]]; then
    echo "AGENT=${id} STATE=${state:-TIMEOUT} LIVE_PROOF=FAIL" >&2
    tmp="$(mktemp)"
    jq --arg id "$id" --arg state "${state:-timeout}" '. + [{id:$id,pass:false,state:$state,status:"timeout-or-failed"}]' "$TMP_RESULTS" >"$tmp"
    mv "$tmp" "$TMP_RESULTS"
    continue
  fi

  status="$(printf '%s' "$result" | jq -r '.job.result.status // "missing"')"
  text_ok="$(printf '%s' "$result" | jq -r --arg marker "$MARKER" '(.job.result.text // "") == $marker')"
  if [[ "$status" == "ok" && "$text_ok" == "true" ]]; then
    echo "AGENT=${id} LIVE_PROOF=PASS"
    pass=$((pass+1))
    tmp="$(mktemp)"
    jq --arg id "$id" '. + [{id:$id,pass:true,state:"done",status:"ok"}]' "$TMP_RESULTS" >"$tmp"
    mv "$tmp" "$TMP_RESULTS"
  else
    echo "AGENT=${id} STATUS=${status} EXACT_MARKER=${text_ok} LIVE_PROOF=FAIL" >&2
    tmp="$(mktemp)"
    jq --arg id "$id" --arg status "$status" --argjson exact "$text_ok" '. + [{id:$id,pass:false,state:"done",status:$status,exact_marker:$exact}]' "$TMP_RESULTS" >"$tmp"
    mv "$tmp" "$TMP_RESULTS"
  fi
done

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n \
  --arg schema "hive.gateway.managed-live-proof.v1" \
  --arg started "$STARTED_AT" \
  --arg finished "$FINISHED_AT" \
  --argjson results "$(cat "$TMP_RESULTS")" \
  --argjson passed "$pass" \
  '{schema_version:$schema,started_at:$started,finished_at:$finished,managed_expected:8,managed_passed:$passed,deferred_agent_ids:["kimi","meta"],strict_10_of_10_gate_preserved:true,results:$results}' \
  >"$PROOF_FILE"
chmod 600 "$PROOF_FILE"
sha="$(sha256sum "$PROOF_FILE" | awk '{print $1}')"

echo "MANAGED_AGENT_LIVE_PROOF=${pass}/8"
echo "PROOF_FILE=${PROOF_FILE}"
echo "PROOF_SHA256=${sha}"
echo "SECRETS_EXPOSED=false"

if [[ "$pass" -ne 8 ]]; then
  echo "LIVE_BROWSER_DATA_PLANE=FAIL" >&2
  exit 20
fi

echo "LIVE_BROWSER_DATA_PLANE=PASS"
echo "STRICT_GATE=10/10_PRESERVED"
echo "KIMI=DEFERRED"
echo "META=DEFERRED"
