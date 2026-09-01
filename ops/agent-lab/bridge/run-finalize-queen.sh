#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/pfarma-ci"
BRANCH="hive-cloud-computer-v0"
PRIVATE_REPO="giovannifidel-collab/hive-alveare"
STATUS_ISSUE=13
REPORT="ops/agent-lab/standard/reports/latest.json"
LOG="$(mktemp)"
STAGE="bootstrap"
ADAPTER_SHA="unknown"

cleanup(){ rm -f "$LOG"; }
trap cleanup EXIT

cd "$ROOT"
command -v git >/dev/null 2>&1 || { echo 'ERROR: git missing'; exit 90; }
command -v gh >/dev/null 2>&1 || { echo 'ERROR: GitHub CLI missing'; exit 91; }
gh auth status >/dev/null 2>&1 || { echo 'ERROR: GitHub CLI not authenticated'; exit 92; }

publish(){
  local state="$1" detail="${2:-}"
  local body
  body="$(node - "$STAGE" "$state" "$detail" "$ADAPTER_SHA" "$REPORT" <<'NODE'
const fs=require('fs');
const [stage,state,detail,sha,report]=process.argv.slice(2);
let passed=null, failedCount=null, failures=[];
try {
  const r=JSON.parse(fs.readFileSync(report,'utf8'));
  passed=Number.isFinite(Number(r.passed_count))?Number(r.passed_count):null;
  failedCount=Number.isFinite(Number(r.failed_count))?Number(r.failed_count):null;
  const cls=(raw)=>{const s=String(raw||'').toUpperCase(); if(s.includes('TIMEOUT'))return 'TIMEOUT'; if(s.includes('BLOCKED'))return 'BLOCKED'; if(s.includes('NOT_IDLE'))return 'NOT_IDLE'; if(s.includes('SUBMIT'))return 'SUBMISSION'; if(s.includes('HEALTH'))return 'HEALTH'; if(s.includes('CDP'))return 'CDP'; return s?'PROBE_FAILED':'UNKNOWN';};
  failures=(r.results||[]).filter(x=>!x.pass).map(x=>({id:String(x.id||'unknown'),class:cls(x.error||x.output?.text||x.health?.text),attempts:Number(x.attempt_count||x.attempts?.length||0)}));
} catch {}
const out=[];
out.push('## HIVE Queen Agent Fabric supervisor','');
out.push(`- State: \`${state}\``);
out.push(`- Stage: \`${stage}\``);
out.push(`- Updated: \`${new Date().toISOString()}\``);
out.push(`- Adapter SHA: \`${sha}\``);
if(detail) out.push(`- Detail: \`${String(detail).replace(/[`\r\n]/g,' ').slice(0,180)}\``);
if(passed!==null) out.push(`- Latest standardization: \`${passed}/10 passed\`, \`${failedCount} failed\``);
if(failures.length){out.push('','### Sanitized failures'); for(const f of failures) out.push(`- \`${f.id}\` — \`${f.class}\` — attempts: \`${f.attempts}\``);}
out.push('','No credentials, cookies, browser-session material, probe tokens or provider response bodies are published here.');
process.stdout.write(out.join('\n'));
NODE
)"
  gh api -X PATCH "repos/${PRIVATE_REPO}/issues/${STATUS_ISSUE}" -f body="$body" >/dev/null
}

STAGE="source-sync"
publish RUNNING entrypoint-started

git fetch origin "$BRANCH"
CURRENT="$(git branch --show-current)"
if [[ "$CURRENT" != "$BRANCH" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    publish BLOCKED "working-tree-dirty-on-${CURRENT:-detached}"
    echo "ERROR: working tree has local changes; refusing automatic branch switch"
    exit 93
  fi
  git switch "$BRANCH"
fi
git pull --ff-only origin "$BRANCH"
ADAPTER_SHA="$(git rev-parse HEAD)"
publish PASSED source-synchronized

STAGE="supervisor"
set +e
bash ops/agent-lab/bridge/finalize-queen-integration.sh 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
set -e

if [[ "$RC" -eq 0 ]]; then
  STAGE="complete"
  publish HIVE_INTEGRATED supervisor-exit-0
  echo 'ENTRYPOINT_RESULT=HIVE_INTEGRATED'
  exit 0
fi

LAST_STAGE="$(grep '^=== .* ===$' "$LOG" | tail -1 | sed -E 's/^=== (.*) ===$/\1/' || true)"
STAGE="${LAST_STAGE:-supervisor}"
publish BLOCKED "supervisor-exit-${RC}"
echo "ENTRYPOINT_RESULT=BLOCKED"
echo "ENTRYPOINT_EXIT_CODE=$RC"
exit "$RC"
