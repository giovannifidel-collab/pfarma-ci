#!/usr/bin/env bash
set -euo pipefail

SOURCE="${1:-}"
DEST="/var/lib/hive-agent-gateway/.hive-agent-lab"
SERVICE_USER="hive"
SERVICE_GROUP="hive"

if [[ -z "$SOURCE" || ! -d "$SOURCE" ]]; then
  echo "Usage: sudo bash migrate-browser-state.sh /path/to/exported/.hive-agent-lab" >&2
  exit 2
fi
[[ "${EUID}" -eq 0 ]] || { echo "ERROR: run as root (sudo)." >&2; exit 1; }
id "$SERVICE_USER" >/dev/null 2>&1 || { echo "ERROR: service user '$SERVICE_USER' does not exist; run install.sh first." >&2; exit 3; }

SOURCE="$(cd "$SOURCE" && pwd)"
if [[ "$SOURCE" == "$DEST" ]]; then
  echo "ERROR: source and destination are identical." >&2
  exit 4
fi

WAS_ACTIVE=0
if systemctl is-active --quiet hive-agent-gateway.service; then
  WAS_ACTIVE=1
  systemctl stop hive-agent-gateway.service
fi

install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$DEST"

echo "HIVE_BROWSER_STATE_MIGRATION=STARTED"
echo "SOURCE=$SOURCE"
echo "DEST=$DEST"

# Preserve provider authentication/profile data while dropping ephemeral runtime
# artifacts. The bridge token is deliberately NOT migrated here; it belongs in
# /etc/hive-agent-gateway/gateway.env and must remain the explicitly controlled
# stable secret.
rsync -a \
  --exclude='*.pid' \
  --exclude='*.log' \
  --exclude='*/Cache/' \
  --exclude='*/Code Cache/' \
  --exclude='*/GPUCache/' \
  --exclude='ShaderCache/' \
  --exclude='GrShaderCache/' \
  --exclude='agent-bridge/token' \
  --exclude='agent-bridge/url' \
  "$SOURCE/" "$DEST/"

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DEST"
chmod 700 "$DEST"

if [[ "$WAS_ACTIVE" == "1" ]]; then
  systemctl start hive-agent-gateway.service
fi

echo "HIVE_BROWSER_STATE_MIGRATION=COMPLETE"
echo "BRIDGE_TOKEN_MIGRATED=false"
echo "RUNTIME_ARTIFACTS_MIGRATED=false"
