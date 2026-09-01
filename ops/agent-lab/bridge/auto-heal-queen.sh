#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BRANCH="hive-cloud-computer-v0"
POLL_SECONDS="${HIVE_AUTO_HEAL_POLL_SECONDS:-20}"
LAST_SHA=""

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
