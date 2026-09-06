#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BRANCH="hive-cloud-computer-v0"
POLL_SECONDS="${HIVE_AUTO_HEAL_POLL_SECONDS:-20}"
STATE_DIR="$HOME/.hive-agent-lab"
LOCK_FILE="$STATE_DIR/auto-heal.lock"
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

while true; do
  git fetch origin "$BRANCH" >/dev/null 2>&1 || { log 'fetch failed; retrying'; sleep "$POLL_SECONDS"; continue; }
  SHA="$(git rev-parse "origin/$BRANCH")"
  if [[ "$SHA" != "$LAST_SHA" ]]; then
    log "new adapter revision $SHA"
    git checkout "$BRANCH" >/dev/null 2>&1 || true
    git reset --hard "origin/$BRANCH" >/dev/null
    LAST_SHA="$SHA"
    set +e
    bash ops/agent-lab/bridge/run-finalize-queen.sh
    RC=$?
    set -e
    if [[ "$RC" == "0" ]]; then
      log 'HIVE/Queen integration completed'
      exit 0
    fi
    log "finalizer stopped with rc=$RC; waiting for next repair commit"
  fi
  sleep "$POLL_SECONDS"
done
