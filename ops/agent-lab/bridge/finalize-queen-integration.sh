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

say(){ printf '\n=== %s ===\n' "$*"; }

say 'SYNC ADAPTER SOURCE'
git pull --ff-only origin hive-cloud-computer-v0
ADAPTER_SHA="$(git rev-parse HEAD)"
echo "ADAPTER_SHA=$ADAPTER_SHA"

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
FULL_OK=0
if run_full_gate; then
  FULL_OK=1
else
  for round in 1 2; do
    echo "STABILIZATION_ROUND=$round/2"
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
  echo 'ERROR: bounded self-healing exhausted; no registry/enrollment state was changed.'
  exit 20
fi

echo 'STANDARDIZATION_STABLE=10/10'

say 'START AUTHENTICATED HIVE AGENT BRIDGE'
bash ops/agent-lab/bridge/start-secure-tunnel.sh
if ! gh secret list -R "$PRIVATE_REPO" | awk '{print $1}' | grep -qx 'HIVE_AGENT_BRIDGE_URL'; then
  echo 'ERROR: HIVE_AGENT_BRIDGE_URL secret was not synchronized'; exit 21
fi
if ! gh secret list -R "$PRIVATE_REPO" | awk '{print $1}' | grep -qx 'HIVE_AGENT_BRIDGE_TOKEN'; then
  echo 'ERROR: HIVE_AGENT_BRIDGE_TOKEN secret was not synchronized'; exit 21
fi
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

say 'QUEEN LIVE 10/10 INTEGRATION + MANAGED ENROLLMENT'
RUN_ID="$(dispatch_and_wait queen-agent-fabric.yml -f "adapter_sha=$ADAPTER_SHA")"
echo "QUEEN_AGENT_FABRIC_RUN=$RUN_ID"
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
[[ "$CLOUD_OK" == "1" ]] || { echo 'ERROR: Queen managed-agent integration gate did not pass; promotion remains fail-closed.'; exit 22; }

say 'VERIFY AUTHORITATIVE PROOF LOCK'
TMP_LOCK="$(mktemp)"
gh api "repos/${PRIVATE_REPO}/contents/ops/queen/agents/PROOF_LOCK.json?ref=main" --jq '.content' | tr -d '\n' | base64 --decode >"$TMP_LOCK"
node - "$TMP_LOCK" <<'NODE'
const fs=require('fs');const p=process.argv[2];const x=JSON.parse(fs.readFileSync(p,'utf8'));
if(x.status!=='HIVE_INTEGRATED'||x.managed_agent_count!==10||x.agent_ids?.length!==10)throw new Error('authoritative proof lock invalid');
console.log('AUTHORITATIVE_PROOF_LOCK=valid');
console.log('MANAGED_AGENTS=10/10');
console.log(`ADAPTER_SHA=${x.adapter_source?.sha||'unknown'}`);
console.log(`PROOF_SHA256=${x.report_sha256||'unknown'}`);
NODE
rm -f "$TMP_LOCK"

say 'QUEEN AUTONOMOUS RUNTIME VERIFICATION'
QUEEN_RUN="$(dispatch_and_wait queen-runtime.yml)"
echo "QUEEN_RUNTIME_RUN=$QUEEN_RUN"
gh run watch "$QUEEN_RUN" -R "$PRIVATE_REPO" --exit-status

say 'HIVE / QUEEN INTEGRATION COMPLETE'
echo 'STANDARDIZED=10/10'
echo 'MANAGED_AGENTS=10/10'
echo 'QUEEN_AGENT_FABRIC=INTEGRATED'
echo 'QUEEN_ROUTING=direct+fallback+parallel'
echo 'RUNTIME_REGISTRY_SYNC=10/10'
echo 'MAX_AUTHORITY=L1'
echo 'FAIL_CLOSED=true'
echo "ADAPTER_SHA=$ADAPTER_SHA"
