#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BRANCH="$(git branch --show-current)"
[[ "$BRANCH" == "hive-cloud-computer-v0" ]] || { echo "ERROR: expected hive-cloud-computer-v0, got ${BRANCH:-detached}"; exit 2; }
command -v gh >/dev/null 2>&1 || { echo 'ERROR: GitHub CLI required'; exit 2; }
gh auth status >/dev/null 2>&1 || { echo 'ERROR: GitHub CLI is not authenticated'; exit 2; }

PRIVATE_REPO="giovannifidel-collab/hive-alveare"
STANDARD="ops/agent-lab/standard/standardize-all.sh"
REPORT="ops/agent-lab/standard/reports/latest.json"
ACTIVE_IDS="kimi,claude,gemini,deepseek,qwen,mistral,perplexity,copilot,duck"
DEFERRED_ID="meta"

say(){ printf '\n=== %s ===\n' "$*"; }

say 'SYNC ADAPTER SOURCE'
git fetch origin hive-cloud-computer-v0
git merge --ff-only FETCH_HEAD
ADAPTER_SHA="$(git rev-parse HEAD)"
echo "ADAPTER_SHA=$ADAPTER_SHA"
echo 'INTEGRATION_MODE=degraded-explicit'
echo "ACTIVE_AGENTS=$ACTIVE_IDS"
echo "DEFERRED_AGENT=$DEFERRED_ID"

say 'STANDARDIZE 9 ACTIVE AGENTS'
set +e
bash "$STANDARD" --only "$ACTIVE_IDS" --attempts 3
STD_RC=$?
set -e
[[ "$STD_RC" -eq 0 ]] || { echo 'ERROR: one or more active agents failed standardization'; exit 20; }

node - "$REPORT" <<'NODE'
const fs=require('fs');
const r=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const expected=['kimi','claude','gemini','deepseek','qwen','mistral','perplexity','copilot','duck'];
const req=r.requested||[];
if(req.length!==9||!expected.every(id=>req.includes(id)))throw new Error('active standardization requested set invalid');
if(r.passed_count!==9||r.failed_count!==0||(r.results||[]).some(x=>!x.pass))throw new Error('active standardization proof invalid');
console.log('ACTIVE_STANDARDIZATION=9/9');
console.log('META_STANDARDIZATION=DEFERRED');
NODE

say 'START AUTHENTICATED HIVE AGENT BRIDGE'
bash ops/agent-lab/bridge/start-secure-tunnel.sh
for secret in HIVE_AGENT_BRIDGE_URL HIVE_AGENT_BRIDGE_TOKEN; do
  gh secret list -R "$PRIVATE_REPO" | awk '{print $1}' | grep -qx "$secret" || { echo "ERROR: $secret secret missing"; exit 21; }
done
echo 'PRIVATE_HIVE_BRIDGE_SECRETS=READY'

latest_dispatch_run(){
  local workflow="$1"
  gh run list -R "$PRIVATE_REPO" --workflow "$workflow" --event workflow_dispatch --limit 1 --json databaseId --jq '.[0].databaseId // empty'
}

dispatch_and_wait(){
  local workflow="$1"; shift
  local before after
  before="$(latest_dispatch_run "$workflow" || true)"
  gh workflow run "$workflow" -R "$PRIVATE_REPO" --ref main "$@"
  for _ in $(seq 1 30); do
    sleep 2
    after="$(latest_dispatch_run "$workflow" || true)"
    if [[ -n "$after" && "$after" != "$before" ]]; then
      echo "$after"
      return 0
    fi
  done
  echo "ERROR: unable to resolve dispatched workflow run for $workflow" >&2
  return 1
}

say 'QUEEN DEGRADED 9/10 INTEGRATION'
RUN_ID="$(dispatch_and_wait queen-agent-fabric-degraded.yml -f "adapter_sha=$ADAPTER_SHA")" || exit 22
echo "QUEEN_AGENT_FABRIC_DEGRADED_RUN=$RUN_ID"
if ! gh run watch "$RUN_ID" -R "$PRIVATE_REPO" --exit-status; then
  echo 'ERROR: degraded Queen integration workflow failed'; exit 22
fi

say 'VERIFY AUTHORITATIVE DEGRADED PROOF LOCK'
TMP_LOCK="$(mktemp)"
gh api "repos/${PRIVATE_REPO}/contents/ops/queen/agents/PROOF_LOCK.json?ref=main" --jq '.content' | tr -d '\n' | base64 --decode >"$TMP_LOCK"
node - "$TMP_LOCK" <<'NODE'
const fs=require('fs');const x=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const expected=['kimi','claude','gemini','deepseek','qwen','mistral','perplexity','copilot','duck'];
if(x.status!=='HIVE_INTEGRATED_DEGRADED')throw new Error(`bad status ${x.status}`);
if(x.integration_mode!=='degraded-explicit'||x.slot_count!==10||x.managed_agent_count!==9||x.deferred_agent_count!==1)throw new Error('degraded counts invalid');
if(x.deferred_agent_ids?.length!==1||x.deferred_agent_ids[0]!=='meta')throw new Error('Meta deferred proof invalid');
if(x.active_agent_ids?.length!==9||!expected.every(id=>x.active_agent_ids.includes(id)))throw new Error('active agent set invalid');
console.log('AUTHORITATIVE_PROOF_LOCK=valid-degraded');
console.log('MANAGED_AGENTS=9/10');
console.log('DEFERRED_AGENT=meta');
console.log(`ADAPTER_SHA=${x.adapter_source?.sha||'unknown'}`);
console.log(`PROOF_SHA256=${x.report_sha256||'unknown'}`);
NODE
rm -f "$TMP_LOCK"

say 'VERIFY AUTHORITATIVE RUNTIME REGISTRY'
TMP_REG="$(mktemp)"
gh api "repos/${PRIVATE_REPO}/contents/ops/queen/runtime/AGENT_REGISTRY.json?ref=main" --jq '.content' | tr -d '\n' | base64 --decode >"$TMP_REG"
node - "$TMP_REG" <<'NODE'
const fs=require('fs');const r=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const all=r.agents||[];
const active=all.filter(a=>a.enrollment==='managed'&&a.certified===true&&a.enabled===true);
const deferred=all.filter(a=>a.enrollment==='deferred'&&a.enabled===false);
if(all.length!==10||active.length!==9||deferred.length!==1||deferred[0]?.id!=='meta')throw new Error('runtime registry degraded contract invalid');
if(r.agent_fabric?.status!=='integrated-degraded'||r.agent_fabric?.managed_count!==9)throw new Error('runtime fabric status invalid');
console.log('RUNTIME_REGISTRY=9_ACTIVE_1_DEFERRED');
NODE
rm -f "$TMP_REG"

say 'QUEEN AUTONOMOUS RUNTIME VERIFICATION'
QUEEN_RUN="$(dispatch_and_wait queen-runtime.yml)" || exit 24
echo "QUEEN_RUNTIME_RUN=$QUEEN_RUN"
gh run watch "$QUEEN_RUN" -R "$PRIVATE_REPO" --exit-status || { echo 'ERROR: Queen runtime verification failed'; exit 24; }

say 'HIVE / QUEEN DEGRADED INTEGRATION COMPLETE'
echo 'INTEGRATION_STATUS=HIVE_INTEGRATED_DEGRADED'
echo 'ACTIVE_STANDARDIZED=9/9'
echo 'MANAGED_AGENTS=9/10'
echo 'DEFERRED_AGENT=meta'
echo 'QUEEN_AGENT_FABRIC=INTEGRATED_DEGRADED'
echo 'QUEEN_ROUTING=direct+fallback+parallel'
echo 'RUNTIME_REGISTRY_SYNC=9_ACTIVE_1_DEFERRED'
echo 'MAX_AUTHORITY=L1'
echo 'FAIL_CLOSED=true'
echo "ADAPTER_SHA=$ADAPTER_SHA"
