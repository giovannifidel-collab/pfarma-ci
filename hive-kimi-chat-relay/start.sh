#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8787}"
CODESPACE_NAME="${CODESPACE_NAME:-${CODESPACE_NAME:-}}"

if [[ -z "${CODESPACE_NAME:-}" ]]; then
  CODESPACE_NAME="$(hostname | sed 's/-.*//')"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required in the Codespace." >&2
  exit 1
fi

# Start relay in background and persist logs in /tmp only.
pkill -f "hive-kimi-chat-relay/server.py" >/dev/null 2>&1 || true
nohup python3 hive-kimi-chat-relay/server.py >/tmp/hive-kimi-chat-relay.log 2>&1 &
PID=$!

for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null

# Codespaces normally auto-forwards a listening port. Set its visibility public.
# If the port has not appeared yet, retry briefly.
for _ in {1..10}; do
  if gh codespace ports visibility "${PORT}:public" -c "$CODESPACE_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
PUBLIC_URL="https://${CODESPACE_NAME}-${PORT}.${DOMAIN}"

echo
echo "HIVE KIMI CHAT RELAY STARTED"
echo "PID: $PID"
echo "Health: ${PUBLIC_URL}/health"
echo "Task URL: ${PUBLIC_URL}/task"
echo "Result URL: ${PUBLIC_URL}/result"
echo
echo "Keep this Codespace running during the test."
echo "Logs: tail -f /tmp/hive-kimi-chat-relay.log"
