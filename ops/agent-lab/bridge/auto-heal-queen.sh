#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BRANCH="hive-cloud-computer-v0"
POLL_SECONDS="${HIVE_AUTO_HEAL_POLL_SECONDS:-20}"
STATE_DIR="$HOME/.hive-agent-lab"
LOCK_FILE="$STATE_DIR/auto-heal.lock"
STATUS_FILE="ops/agent-lab/bridge/runtime-auto-heal-status.json"
LAST_SHA=""
mkdir -p "$STATE_DIR"

# Single-instance guard. A second launcher exits immediately instead of racing
# the active finalizer against the same git workspace and standardization reports.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '[%s] auto-heal already running; exiting duplicate launcher\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 0
fi

log(){ printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

publish_failure(){
  local sha="$1" rc="$2" hint
  case "$rc" in
    90) hint='git-missing' ;;
    91) hint='github-cli-missing' ;;
    93) hint='dirty-worktree' ;;
    94) hint='private-auth-strict-path' ;;
    95) hint='invalid-public-bridge-url' ;;
    96) hint='public-runner-dispatch-failed' ;;
    *) hint='bridge-or-tunnel-recovery-failed' ;;
  esac
  python3 - "$sha" "$rc" "$hint" >"$STATUS_FILE" <<'PY'
import json, sys
print(json.dumps({
  'status':'BLOCKED',
  'adapter_sha':sys.argv[1],
  'finalizer_rc':int(sys.argv[2]),
  'phase_hint':sys.argv[3],
  'token_exposed':False
}, indent=2, sort_keys=True))
PY
  git config user.name 'HIVE Auto Heal'
  git config user.email 'hive-auto-heal@users.noreply.github.com'
  git add "$STATUS_FILE"
  if ! git diff --cached --quiet; then
    git commit -m 'chore(hive): publish autonomous Queen recovery status'
    git push origin "HEAD:${BRANCH}" || true
  fi
}

while true; do
  git fetch origin "$BRANCH" >/dev/null 2>&1 || { log 'fetch failed; retrying'; sleep "$POLL_SECONDS"; continue; }
  SHA="$(git rev-parse "origin/$BRANCH")"
  if [[ "$SHA" != "$LAST_SHA" ]]; then
    log "new adapter revision $SHA"
    git checkout "$BRANCH" >/dev/null 2>&1 || true
    git reset --hard "origin/$BRANCH" >/dev/null
    LAST_SHA="$SHA"
    set +e
    # Close the single-instance lock FD before launching the finalizer. Long-lived
    # descendants such as tailscaled/cloudflared/server.mjs must never inherit it,
    # otherwise a killed controller can leave an apparently stale lock forever.
    bash ops/agent-lab/bridge/run-finalize-queen.sh 9>&-
    RC=$?
    set -e
    if [[ "$RC" == "0" ]]; then
      # run-finalize-queen.sh owns the autonomous public-runner dispatch. Do not
      # dispatch a second copy here; exit once the handoff was created.
      log 'Queen recovery handoff completed by finalizer'
      exit 0
    fi
    log "finalizer stopped with rc=$RC; publishing safe recovery status"
    publish_failure "$SHA" "$RC"
  fi
  sleep "$POLL_SECONDS"
done
