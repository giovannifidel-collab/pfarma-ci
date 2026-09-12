#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PORT="${HIVE_AGENT_BRIDGE_PORT:-9240}"
STATE="$HOME/.hive-agent-lab/agent-bridge"
PERSIST_STATE="/workspaces/.hive-agent-lab/agent-bridge"
TOKEN_FILE="$PERSIST_STATE/token"
LEGACY_TOKEN_FILE="$STATE/token"
URL_FILE="$STATE/url"
SERVER_LOG="$STATE/server.log"
TUNNEL_LOG="$STATE/tunnel.log"
CLOUDFLARED="$HOME/.local/bin/cloudflared"
mkdir -p "$STATE" "$HOME/.local/bin"
sudo mkdir -p "$PERSIST_STATE"
chmod 700 "$STATE"
sudo chmod 700 "$PERSIST_STATE"

# Keep the bearer token stable across Codespace container rebuilds. Migrate the
# pre-existing token so the already configured public-runner secret remains valid.
if [[ ! -f "$TOKEN_FILE" && -f "$LEGACY_TOKEN_FILE" && ! -L "$LEGACY_TOKEN_FILE" ]]; then
  sudo cp "$LEGACY_TOKEN_FILE" "$TOKEN_FILE"
fi
if [[ ! -f "$TOKEN_FILE" ]]; then
  umask 077
  openssl rand -hex 32 | sudo tee "$TOKEN_FILE" >/dev/null
fi
sudo chmod 600 "$TOKEN_FILE"
rm -f "$LEGACY_TOKEN_FILE"
ln -s "$TOKEN_FILE" "$LEGACY_TOKEN_FILE"
TOKEN="$(sudo cat "$TOKEN_FILE")"

port_open(){ timeout 1 bash -c ">/dev/tcp/127.0.0.1/$1" >/dev/null 2>&1; }

if ! port_open "$PORT" || ! curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  pkill -f "ops/agent-lab/bridge/server.mjs" >/dev/null 2>&1 || true
  : >"$SERVER_LOG"
  nohup env HIVE_AGENT_BRIDGE_PORT="$PORT" HIVE_AGENT_BRIDGE_TOKEN="$TOKEN" \
    node ops/agent-lab/bridge/server.mjs >"$SERVER_LOG" 2>&1 &
  echo $! >"$STATE/server.pid"
  for _ in {1..80}; do
    curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
    sleep 0.25
  done
fi
curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null

PUBLIC_URL=""
PUBLIC_MODE=""

# Prefer the stable GitHub Codespaces port-forwarding endpoint. Bound this probe
# so a transient gh/Codespaces API stall cannot block the Cloudflare fallback.
if [[ -n "${CODESPACE_NAME:-}" && -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]] && command -v gh >/dev/null 2>&1; then
  if timeout 15s gh codespace ports visibility "${PORT}:public" -c "$CODESPACE_NAME" >/dev/null 2>&1; then
    CANDIDATE="https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
    for _ in {1..40}; do
      if curl -fsS --max-time 10 "$CANDIDATE/health" >/dev/null 2>&1; then
        PUBLIC_URL="$CANDIDATE"
        PUBLIC_MODE="codespaces-port"
        break
      fi
      sleep 0.5
    done
  fi
fi

if [[ -z "$PUBLIC_URL" ]]; then
  if [[ ! -x "$CLOUDFLARED" ]]; then
    ARCH="$(uname -m)"
    case "$ARCH" in
      x86_64|amd64) ASSET="cloudflared-linux-amd64" ;;
      aarch64|arm64) ASSET="cloudflared-linux-arm64" ;;
      *) echo "ERROR: unsupported architecture: $ARCH" >&2; exit 1 ;;
    esac
    curl -fL --retry 3 --connect-timeout 10 \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/${ASSET}" \
      -o "$CLOUDFLARED"
    chmod 700 "$CLOUDFLARED"
  fi

  pkill -f "cloudflared tunnel.*127.0.0.1:${PORT}" >/dev/null 2>&1 || true
  : >"$TUNNEL_LOG"
  nohup "$CLOUDFLARED" tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" >"$TUNNEL_LOG" 2>&1 &
  echo $! >"$STATE/tunnel.pid"

  for _ in {1..120}; do
    PUBLIC_URL="$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n1 || true)"
    [[ -n "$PUBLIC_URL" ]] && break
    sleep 0.25
  done
  [[ -n "$PUBLIC_URL" ]] || { echo "ERROR: tunnel URL unavailable" >&2; tail -n 80 "$TUNNEL_LOG" >&2; exit 1; }
  PUBLIC_MODE="cloudflare-quick-tunnel"
else
  pkill -f "cloudflared tunnel.*127.0.0.1:${PORT}" >/dev/null 2>&1 || true
fi

printf '%s\n' "$PUBLIC_URL" >"$URL_FILE"
chmod 600 "$URL_FILE"

for _ in {1..30}; do
  curl -fsS --max-time 10 "$PUBLIC_URL/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS --max-time 10 "$PUBLIC_URL/health" >/dev/null

SECRETS_SYNCED=false
if [[ "${HIVE_SKIP_SECRET_SYNC:-0}" != "1" ]] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  printf '%s' "$PUBLIC_URL" | gh secret set HIVE_AGENT_BRIDGE_URL -R giovannifidel-collab/hive-alveare
  printf '%s' "$TOKEN" | gh secret set HIVE_AGENT_BRIDGE_TOKEN -R giovannifidel-collab/hive-alveare
  SECRETS_SYNCED=true
fi

echo "HIVE_AGENT_BRIDGE_TUNNEL=READY"
echo "BRIDGE_PROTOCOL=async-job-v1"
echo "PUBLIC_MODE=$PUBLIC_MODE"
echo "PUBLIC_HEALTH=${PUBLIC_URL}/health"
echo "HIVE_SECRETS_SYNCED=${SECRETS_SYNCED}"
echo "TOKEN_EXPOSED=false"
echo "STATE_DIR=$STATE"
echo "TOKEN_STATE_DIR=$PERSIST_STATE"
