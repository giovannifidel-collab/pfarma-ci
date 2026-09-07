#!/usr/bin/env bash
set -euo pipefail

SOCKET="/var/run/tailscale/tailscaled.sock"
PERSIST_DIR="/workspaces/.hive-tailscale"
STATE_FILE="$PERSIST_DIR/tailscaled.state"
LOG_FILE="$HOME/.hive-agent-lab/tailscale.log"

mkdir -p "$HOME/.hive-agent-lab"
sudo mkdir -p /var/run/tailscale "$PERSIST_DIR"
sudo chmod 700 "$PERSIST_DIR"

if ! command -v tailscale >/dev/null 2>&1 || ! command -v tailscaled >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sudo sh
fi

# One-time migration from the older non-persistent location, if present.
if [[ ! -s "$STATE_FILE" && -s /var/lib/tailscale/tailscaled.state ]]; then
  sudo cp /var/lib/tailscale/tailscaled.state "$STATE_FILE"
  sudo chmod 600 "$STATE_FILE"
fi

sudo pkill tailscaled >/dev/null 2>&1 || true
sudo nohup tailscaled \
  --tun=userspace-networking \
  --state="$STATE_FILE" \
  --socket="$SOCKET" \
  >"$LOG_FILE" 2>&1 &

for _ in {1..40}; do
  sudo tailscale --socket="$SOCKET" status >/dev/null 2>&1 && break
  sleep 0.25
done

if ! sudo tailscale --socket="$SOCKET" up --ssh >/dev/null 2>&1; then
  echo "TAILSCALE_AUTH_REQUIRED_OR_START_FAILED" >&2
  exit 1
fi

sudo tailscale --socket="$SOCKET" status
