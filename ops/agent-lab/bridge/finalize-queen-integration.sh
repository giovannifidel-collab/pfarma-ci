#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BRANCH="$(git branch --show-current)"
[[ "$BRANCH" == "hive-cloud-computer-v0" ]] || { echo "ERROR: expected hive-cloud-computer-v0, got ${BRANCH:-detached}"; exit 2; }
command -v gh >/dev/null 2>&1 || { echo 'ERROR: GitHub CLI required'; exit 2; }
gh auth status >/dev/null 2>&1 || { echo 'ERROR: GitHub CLI is not authenticated'; exit 2; }

PRIVATE_REPO="giovannifidel-collab/hive-alveare"
STATUS_ISSUE=13
STANDARD="ops/agent-lab/standard/standardize-all.sh"
REPORT="ops/agent-lab/standard/reports/latest.json"
ADAPTER_SHA="unknown"

say(){ printf '\n=== %s ===\n' "$*"; }

publish_status(){
  local stage="$1" state="$2" detail="${3:-}"
  local tmp
  tmp="$(mktemp)"
  node - "$stage" "$state" "$detail" "$ADAPTER_SHA" "$REPORT" >"$tmp" <<'NODE' || true
const fs=require('fs');
const [stage,state,detail,adapterSha,reportPath]=process.argv.slice(2);
let summary={passed:null,failed_count:null,failures:[]};
try{
  const r=JSON.parse(fs.readFileSync(reportPath,'utf8'));
  const cls=(raw)=>{
    const s=String(raw||'').toUpperCase();
    if(s.includes('TIMEOUT'))return 'TIMEOUT';
    if(s.includes('BLOCKED'))return 'BLOCKED';
    if(s.includes('NOT_IDLE'))return 'NOT_IDLE';
    if(s.includes('PROMPT_NOT_SUBMITTED')||s.includes('SUBMIT'))return 'SUBMISSION';
    if(s.includes('HEALTH'))return 'HEALTH';
    if(s.includes('CDP'))return 'CDP';
    return s?'PROBE_FAILED':'UNKNOWN';
  };
  summary={
    passed:Number.isFinite(Number(r.passed_count))?Number(r.passed_count):null,
    failed_count:Number.isFinite(Number(r.failed_count))?Number(r.failed_count):null,
    failures:(r.results||[]).filter(x=>!x.pass).map(x=>({
      id:String(x.id||'unknown'),
      class:cls(x.error||x.output?.text||x.health?.text),
      attempts:Number(x.attempt_count||x.attempts?.length||0)
    }))
  };
}catch{}
const stamp=new Date().toISOString();
console.log('## HIVE Queen Agent Fabric supervisor');
console.log('');
console.log(`- State: \`${state}\``);
console.log(`- Stage: \`${stage}\``);
console.log(`- Updated: \`${stamp}\``);
console.log(`- Adapter SHA: \`${adapterSha}\``);
if(detail)console.log(`- Detail: \`${String(detail).replace(/[`\r\n]/g,' ').slice(0,180)}\``);
if(summary.passed!==null)console.log(`- Latest standardization: \`${summary.passed}/10 passed\`, \`${summary.failed_count} failed\``);
if(summary.failures.length){
  console.log('');
  console.log('### Sanitized failures');
  for(const f of summary.failures)console.log(`- \`${f.id}\` — \`${f.class}\` — attempts: \`${f.attempts}\``);
}
console.log('');
console.log('No credentials, cookies, browser-session material, probe tokens or provider response bodies are published here.');
NODE
  gh issue edit "$STATUS_ISSUE" -R "$PRIVATE_REPO" --body-file "$tmp" >/dev/null 2>&1 || true
  rm -f "$tmp"
}

say 'SYNC ADAPTER SOURCE'
git pull --ff-only origin hive-cloud-computer-v0
ADAPTER_SHA="$(git rev-parse HEAD)"
echo "ADAPTER_SHA=$ADAPTER_SHA"
publish_status sync RUNNING source-synchronized

run_full_gate(){
  set +e
  bash "$STANDARD" --attempts 3
  local rc=$?
  set -e
  return "$rc"
}
run_failed_gate(){
  set +e
  bash "$STANDARD" --retry-failed --attempts 3
  local rc=$?
  set -e
  return "$rc"
}

say 'SELF-HEALING 10-AGENT STANDARDIZATION'
publish_status standardization RUNNING full-gate
FULL_OK=0
if run_full_gate; then
  FULL_OK=1
else
  for round in 1 2; do
    echo "STABILIZATION_ROUND=$round/2"
    publish_status standardization RUNNING "recovery-round-${round}"
    run_failed_gate || true
    if run_full_gate; then
      FULL_OK=1
      break
    fi
  done
fi

if [[ "$FULL_OK" != "1" ]]; then
  say 'STANDARDIZATION BLOCKED'
  node - "$REPORT" <<'NODE' || true
  const fs=require('fs');const p=process.argv[2];
  try{
    const r=JSON.parse(fs.readFileSync(p,'utf8'));
    const failed=(r.results||[]).filter(x=>!x.pass).map(x=>({id:x.id,error:x.error||x.output?.text||x.health?.text||'unknown',attempts:x.attempt_count||x.attempts?.length||0}));
    console.log(JSON.stringify({passed:r.passed_count,failed_count:r.failed_count,failed},null,2));
  }catch(e){console.error(e.message)}
NODE
  publish_status standardization BLOCKED bounded-self-healing-exhausted
  echo 'ERROR: bounded self-healing exhausted; no registry/enrollment state was changed.'
  exit 20
fi

echo 'STANDARDIZATION_STABLE=10/10'
publish_status standardization PASSED 10-of-10

say 'START AUTHENTICATED HIVE AGENT BRIDGE'
publish_status bridge RUNNING starting-secure-tunnel
if ! bash ops/agent-lab/bridge/start-secure-tunnel.sh; then
  publish_status bridge BLOCKED secure-tunnel-start-failed
  exit 21
fi
if ! gh secret list -R "$PRIVATE_REPO" | awk '{print $1}' | grep -qx 'HIVE_AGENT_BRIDGE_URL'; then
  publish_status bridge BLOCKED bridge-url-secret-missing
  echo 'ERROR: HIVE_AGENT_BRIDGE_URL secret was not synchronized'; exit 21
fi
if ! gh secret list -R "$PRIVATE_REPO" | awk '{print $1}' | grep -qx 'HIVE_AGENT_BRIDGE_TOKEN'; then
  publish_status bridge BLOCKED bridge-token-secret-missing
  echo 'ERROR: HIVE_AGENT_BRIDGE_TOKEN secret was not synchronized'; exit 21
fi
echo 'PRIVATE_HIVE_BRIDGE_SECRETS=READY'
publish_status bridge PASSED authenticated-bridge-ready

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

say 'QUEEN LIVE 10/10 INTEGRATION + MANAGED ENROLLMENT'
publish_status queen-integration RUNNING dispatching-private-gate
if ! RUN_ID="$(dispatch_and_wait queen-agent-fabric.yml -f "adapter_sha=$ADAPTER_SHA")"; then
  publish_status queen-integration BLOCKED workflow-dispatch-failed
  exit 22
fi
echo "QUEEN_AGENT_FABRIC_RUN=$RUN_ID"
publish_status queen-integration RUNNING "run-${RUN_ID}"
CLOUD_OK=0
for cloud_attempt in 1 2 3; do
  echo "CLOUD_INTEGRATION_ATTEMPT=$cloud_attempt/3"
  if gh run watch "$RUN_ID" -R "$PRIVATE_REPO" --exit-status; then
    CLOUD_OK=1
    break
  fi
  if [[ "$cloud_attempt" -lt 3 ]]; then
    echo 'Cloud integration run failed; requesting bounded rerun...'
    gh run rerun "$RUN_ID" -R "$PRIVATE_REPO"
    sleep 3
  fi
done
if [[ "$CLOUD_OK" != "1" ]]; then
  publish_status queen-integration BLOCKED "run-${RUN_ID}-failed"
  echo 'ERROR: Queen managed-agent integration gate did not pass; promotion remains fail-closed.'
  exit 22
fi
publish_status queen-integration PASSED "run-${RUN_ID}"

say 'VERIFY AUTHORITATIVE PROOF LOCK'
TMP_LOCK="$(mktemp)"
if ! gh api "repos/${PRIVATE_REPO}/contents/ops/queen/agents/PROOF_LOCK.json?ref=main" --jq '.content' | tr -d '\n' | base64 --decode >"$TMP_LOCK"; then
  rm -f "$TMP_LOCK"
  publish_status proof-lock BLOCKED authoritative-proof-lock-missing
  exit 23
fi
if ! node - "$TMP_LOCK" <<'NODE'
const fs=require('fs');const p=process.argv[2];const x=JSON.parse(fs.readFileSync(p,'utf8'));
if(x.status!=='HIVE_INTEGRATED'||x.managed_agent_count!==10||x.agent_ids?.length!==10)throw new Error('authoritative proof lock invalid');
console.log('AUTHORITATIVE_PROOF_LOCK=valid');
console.log('MANAGED_AGENTS=10/10');
console.log(`ADAPTER_SHA=${x.adapter_source?.sha||'unknown'}`);
console.log(`PROOF_SHA256=${x.report_sha256||'unknown'}`);
NODE
then
  rm -f "$TMP_LOCK"
  publish_status proof-lock BLOCKED authoritative-proof-lock-invalid
  exit 23
fi
rm -f "$TMP_LOCK"
publish_status proof-lock PASSED authoritative-proof-verified

say 'QUEEN AUTONOMOUS RUNTIME VERIFICATION'
publish_status queen-runtime RUNNING dispatching-runtime-verification
if ! QUEEN_RUN="$(dispatch_and_wait queen-runtime.yml)"; then
  publish_status queen-runtime BLOCKED runtime-dispatch-failed
  exit 24
fi
echo "QUEEN_RUNTIME_RUN=$QUEEN_RUN"
if ! gh run watch "$QUEEN_RUN" -R "$PRIVATE_REPO" --exit-status; then
  publish_status queen-runtime BLOCKED "run-${QUEEN_RUN}-failed"
  exit 24
fi
publish_status complete HIVE_INTEGRATED "managed-10-of-10-runtime-${QUEEN_RUN}"

say 'HIVE / QUEEN INTEGRATION COMPLETE'
echo 'STANDARDIZED=10/10'
echo 'MANAGED_AGENTS=10/10'
echo 'QUEEN_AGENT_FABRIC=INTEGRATED'
echo 'QUEEN_ROUTING=direct+fallback+parallel'
echo 'RUNTIME_REGISTRY_SYNC=10/10'
echo 'MAX_AUTHORITY=L1'
echo 'FAIL_CLOSED=true'
echo "ADAPTER_SHA=$ADAPTER_SHA"
