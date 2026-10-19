#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${HIVE_AGENTLAB_WEB_PORT:-6080}"
ROOT="${HIVE_AGENTLAB_HOST_DIR:-$HOME/.hive-agent-lab/browser-host}"
PASSWORD_TEXT="$ROOT/vnc.password"

if [[ -z "${CODESPACE_NAME:-}" ]]; then
  echo "ERROR: CODESPACE_NAME non disponibile."
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI (gh) non disponibile."
  exit 1
fi

if [[ ! -f "$PASSWORD_TEXT" ]]; then
  echo "ERROR: password VNC non ancora generata. Esegui prima ensure-desktop.sh."
  exit 1
fi

gh codespace ports visibility "${WEB_PORT}:public" -c "$CODESPACE_NAME"

CACHE_BUST="$(date +%s)"
DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
URL="https://${CODESPACE_NAME}-${WEB_PORT}.${DOMAIN}/vnc.html?autoconnect=true&resize=scale&path=websockify&logging=debug&_=${CACHE_BUST}"

cat <<EOF
TEMPORARY_PUBLIC_DESKTOP=READY
PORT=${WEB_PORT}
VISIBILITY=public
URL=${URL}
PASSWORD_COMMAND=cat ${PASSWORD_TEXT}
IMPORTANT: usa la password solo nella schermata noVNC e non incollarla in chat.
Quando hai finito il login esegui: bash $(dirname "$0")/close-private.sh
EOF
