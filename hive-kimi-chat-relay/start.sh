#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8787}"
CODESPACE_NAME="${CODESPACE_NAME:-}"
OPENCLAW_PREFIX="$HOME/.openclaw"
LOG="/tmp/hive-kimi-chat-relay.log"

if [[ -z "$CODESPACE_NAME" ]]; then
  CODESPACE_NAME="$(hostname)"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required in the Codespace." >&2
  exit 1
fi

NODE_BIN=""
if command -v node >/dev/null 2>&1; then
  NODE_BIN="$(command -v node)"
else
  for d in "$OPENCLAW_PREFIX"/tools/node-v*/bin; do
    if [[ -x "$d/node" ]]; then
      NODE_BIN="$d/node"
    fi
  done
fi

if [[ -z "$NODE_BIN" || ! -x "$NODE_BIN" ]]; then
  echo "Node runtime not found. OpenClaw bootstrap should have installed one." >&2
  exit 1
fi

echo "Using Node: $NODE_BIN"

# Start relay in background and persist logs in /tmp only.
pkill -f "hive-kimi-chat-relay/server.mjs" >/dev/null 2>&1 || true
: >"$LOG"
nohup "$NODE_BIN" hive-kimi-chat-relay/server.mjs >"$LOG" 2>&1 &
PID=$!

READY=0
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    READY=1
    break
  fi
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    echo "Relay process exited before becoming ready. Log:" >&2
    cat "$LOG" >&2 || true
    exit 1
  fi
  sleep 0.5
done

if [[ "$READY" != "1" ]]; then
  echo "Relay did not become healthy on port $PORT. Log:" >&2
  cat "$LOG" >&2 || true
  exit 1
fi

PUBLIC_OK=0
for _ in {1..10}; do
  if gh codespace ports visibility "${PORT}:public" -c "$CODESPACE_NAME" >/dev/null 2>&1; then
    PUBLIC_OK=1
    break
  fi
  sleep 1
done

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
PUBLIC_URL="https://${CODESPACE_NAME}-${PORT}.${DOMAIN}"

echo
echo "HIVE KIMI CHAT RELAY STARTED"
echo "PID: $PID"
echo "Codespace: $CODESPACE_NAME"
echo "Health: ${PUBLIC_URL}/health"
echo "Task URL: ${PUBLIC_URL}/task"
echo "Result URL: ${PUBLIC_URL}/result"
if [[ "$PUBLIC_OK" != "1" ]]; then
  echo "WARNING: automatic public visibility did not confirm. Open the VS Code Ports panel and set port ${PORT} to Public manually."
fi
echo
echo "Keep this Codespace running during the test."
echo "Logs: tail -f $LOG"
