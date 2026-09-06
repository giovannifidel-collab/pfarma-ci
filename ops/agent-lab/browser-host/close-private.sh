#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${HIVE_AGENTLAB_WEB_PORT:-6080}"

if [[ -z "${CODESPACE_NAME:-}" ]]; then
  echo "ERROR: CODESPACE_NAME non disponibile."
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI (gh) non disponibile."
  exit 1
fi

gh codespace ports visibility "${WEB_PORT}:private" -c "$CODESPACE_NAME"

echo "TEMPORARY_PUBLIC_DESKTOP=CLOSED"
echo "PORT=${WEB_PORT}"
echo "VISIBILITY=private"
