#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8787}"
LOCAL_BIN="$HOME/.local/bin"
CLOUDFLARED="$LOCAL_BIN/cloudflared"
RELAY_LOG="/tmp/hive-kimi-chat-relay.log"
TUNNEL_LOG="/tmp/hive-kimi-cloudflare-tunnel.log"

mkdir -p "$LOCAL_BIN"

# Ensure relay is running.
if ! curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "Starting HIVE Kimi relay on port ${PORT}..."
  bash hive-kimi-chat-relay/start.sh >/tmp/hive-kimi-chat-relay-start.out 2>&1 || {
    cat /tmp/hive-kimi-chat-relay-start.out >&2 || true
    exit 1
  }
fi

curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null

# Install cloudflared user-space if needed. No Cloudflare account or token required for Quick Tunnels.
if [[ ! -x "$CLOUDFLARED" ]]; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64|amd64) ASSET="cloudflared-linux-amd64" ;;
    aarch64|arm64) ASSET="cloudflared-linux-arm64" ;;
    *) echo "Unsupported architecture for cloudflared: $ARCH" >&2; exit 1 ;;
  esac
  echo "Installing cloudflared user-space..."
  curl -fL --retry 3 --connect-timeout 10 \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/${ASSET}" \
    -o "$CLOUDFLARED"
  chmod 700 "$CLOUDFLARED"
fi

# Stop only an older HIVE quick tunnel launched for this relay.
pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" >/dev/null 2>&1 || true
: >"$TUNNEL_LOG"

nohup "$CLOUDFLARED" tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" \
  >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

PUBLIC_URL=""
for _ in {1..60}; do
  PUBLIC_URL="$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n 1 || true)"
  if [[ -n "$PUBLIC_URL" ]]; then
    break
  fi
  if ! kill -0 "$TUNNEL_PID" >/dev/null 2>&1; then
    echo "Cloudflare tunnel exited before publishing a URL." >&2
    cat "$TUNNEL_LOG" >&2 || true
    exit 1
  fi
  sleep 0.5
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Cloudflare Quick Tunnel URL was not obtained in time." >&2
  cat "$TUNNEL_LOG" >&2 || true
  exit 1
fi

# Verify the public path itself, not only localhost.
PUBLIC_OK=0
for _ in {1..20}; do
  if curl -fsS --max-time 10 "$PUBLIC_URL/health" >/dev/null 2>&1; then
    PUBLIC_OK=1
    break
  fi
  sleep 0.5
done

if [[ "$PUBLIC_OK" != "1" ]]; then
  echo "Tunnel URL was created but public /health did not become reachable." >&2
  echo "URL: $PUBLIC_URL" >&2
  tail -n 80 "$TUNNEL_LOG" >&2 || true
  exit 1
fi

echo
echo "HIVE KIMI CLOUDFLARE RELAY READY"
echo "Relay PID: $(pgrep -f 'hive-kimi-chat-relay/server.mjs' | head -n 1 || true)"
echo "Tunnel PID: $TUNNEL_PID"
echo "Health: ${PUBLIC_URL}/health"
echo "Task URL: ${PUBLIC_URL}/task"
echo "Result URL: ${PUBLIC_URL}/result"
echo "Work URL: ${PUBLIC_URL}/work"
echo "Work Result URL: ${PUBLIC_URL}/work-result"
echo
echo "Keep this Codespace running during the test."
echo "Tunnel log: $TUNNEL_LOG"
echo "Relay log: $RELAY_LOG"
