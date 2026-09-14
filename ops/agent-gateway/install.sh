#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/giovannifidel-collab/pfarma-ci.git"
BRANCH="hive-cloud-computer-v0"
SERVICE_USER="hive"
SERVICE_GROUP="hive"
APP_ROOT="/opt/hive"
APP_DIR="${APP_ROOT}/pfarma-ci"
STATE_DIR="/var/lib/hive-agent-gateway"
CONFIG_DIR="/etc/hive-agent-gateway"
GATEWAY_ENV="${CONFIG_DIR}/gateway.env"
CLOUDFLARE_ENV="${CONFIG_DIR}/cloudflare.env"
BRIDGE_TOKEN_FILE=""
CLOUDFLARE_TOKEN_FILE=""
NO_START=0

usage(){
  cat <<'EOF'
Usage: sudo bash install.sh [options]

Options:
  --token-file PATH             protected file containing the EXISTING stable bridge token
  --cloudflare-token-file PATH  protected file containing a Cloudflare Named Tunnel token
  --no-start                    install/update only; do not enable/start services
  -h, --help                    show this help

The installer never generates a new HIVE_AGENT_BRIDGE_TOKEN.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token-file) BRIDGE_TOKEN_FILE="${2:?missing path}"; shift 2 ;;
    --cloudflare-token-file) CLOUDFLARE_TOKEN_FILE="${2:?missing path}"; shift 2 ;;
    --no-start) NO_START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || { echo "ERROR: run as root (sudo)." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive

need_cmd(){ command -v "$1" >/dev/null 2>&1; }

env_value(){
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  awk -F= -v k="$key" '$1==k {sub(/^[^=]*=/,""); print; exit}' "$file"
}

install_env_value(){
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp)"
  if [[ -f "$file" ]]; then
    grep -v "^${key}=" "$file" >"$tmp" || true
  fi
  printf '%s=%s\n' "$key" "$value" >>"$tmp"
  install -m 600 -o root -g "$SERVICE_GROUP" "$tmp" "$file"
  rm -f "$tmp"
}

read_secret_file(){
  local file="$1"
  [[ -f "$file" ]] || { echo "ERROR: secret file not found: $file" >&2; exit 3; }
  tr -d '\r\n' <"$file"
}

echo "=== HIVE AGENT GATEWAY v1 INSTALL ==="

echo "[1/7] Installing base OS dependencies..."
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg jq openssl rsync \
  xvfb openbox x11vnc novnc websockify dbus-x11 x11-utils

NODE_MAJOR=0
if need_cmd node; then
  NODE_MAJOR="$(node -p "Number(process.versions.node.split('.')[0])" 2>/dev/null || echo 0)"
fi
if (( NODE_MAJOR < 22 )); then
  echo "[2/7] Installing Node.js 22 LTS runtime..."
  NS="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/setup_22.x -o "$NS"
  bash "$NS"
  rm -f "$NS"
  apt-get install -y nodejs
else
  echo "[2/7] Node.js ${NODE_MAJOR} already suitable."
fi

NODE_MAJOR="$(node -p "Number(process.versions.node.split('.')[0])")"
(( NODE_MAJOR >= 22 )) || { echo "ERROR: Node.js >=22 required." >&2; exit 4; }

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$STATE_DIR" --shell /bin/bash "$SERVICE_USER"
fi
install -d -m 0755 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$APP_ROOT"
install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$STATE_DIR"
install -d -m 0750 -o root -g "$SERVICE_GROUP" "$CONFIG_DIR"

echo "[3/7] Installing/updating repository checkout..."
if [[ -d "$APP_DIR/.git" ]]; then
  sudo -u "$SERVICE_USER" git -C "$APP_DIR" fetch --prune origin "$BRANCH"
  sudo -u "$SERVICE_USER" git -C "$APP_DIR" checkout "$BRANCH"
  sudo -u "$SERVICE_USER" git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
elif [[ -e "$APP_DIR" ]]; then
  echo "ERROR: $APP_DIR exists but is not a git checkout." >&2
  exit 5
else
  sudo -u "$SERVICE_USER" git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
fi

# Runtime configuration is created once and preserved on later installs.
if [[ ! -f "$GATEWAY_ENV" ]]; then
  install -m 600 -o root -g "$SERVICE_GROUP" \
    "$APP_DIR/ops/agent-gateway/gateway.env.example" "$GATEWAY_ENV"
fi
if [[ ! -f "$CLOUDFLARE_ENV" ]]; then
  install -m 600 -o root -g "$SERVICE_GROUP" \
    "$APP_DIR/ops/agent-gateway/cloudflare.env.example" "$CLOUDFLARE_ENV"
fi

if [[ -n "$BRIDGE_TOKEN_FILE" ]]; then
  BRIDGE_TOKEN="$(read_secret_file "$BRIDGE_TOKEN_FILE")"
  (( ${#BRIDGE_TOKEN} >= 32 )) || { echo "ERROR: bridge token is shorter than 32 characters." >&2; exit 6; }
  install_env_value "$GATEWAY_ENV" HIVE_AGENT_BRIDGE_TOKEN "$BRIDGE_TOKEN"
  unset BRIDGE_TOKEN
fi

if [[ -n "$CLOUDFLARE_TOKEN_FILE" ]]; then
  CF_TUNNEL_TOKEN="$(read_secret_file "$CLOUDFLARE_TOKEN_FILE")"
  [[ -n "$CF_TUNNEL_TOKEN" ]] || { echo "ERROR: Cloudflare tunnel token is empty." >&2; exit 7; }
  install_env_value "$CLOUDFLARE_ENV" HIVE_CLOUDFLARE_TUNNEL_TOKEN "$CF_TUNNEL_TOKEN"
  unset CF_TUNNEL_TOKEN
fi

echo "[4/7] Installing cloudflared binary..."
if ! need_cmd cloudflared; then
  case "$(uname -m)" in
    x86_64|amd64) CF_ASSET="cloudflared-linux-amd64" ;;
    aarch64|arm64) CF_ASSET="cloudflared-linux-arm64" ;;
    *) echo "ERROR: unsupported cloudflared architecture: $(uname -m)" >&2; exit 8 ;;
  esac
  TMP_CF="$(mktemp)"
  curl -fL --retry 3 --connect-timeout 10 \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/${CF_ASSET}" \
    -o "$TMP_CF"
  install -m 0755 "$TMP_CF" /usr/local/bin/cloudflared
  rm -f "$TMP_CF"
fi

echo "[5/7] Installing systemd units..."
install -m 0644 "$APP_DIR/ops/agent-gateway/systemd/hive-agent-gateway.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/ops/agent-gateway/systemd/hive-agent-gateway-health.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/ops/agent-gateway/systemd/hive-agent-gateway-health.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/ops/agent-gateway/systemd/hive-agent-gateway-cloudflared.service" /etc/systemd/system/
systemctl daemon-reload

BRIDGE_TOKEN_PRESENT="$(env_value "$GATEWAY_ENV" HIVE_AGENT_BRIDGE_TOKEN)"
CF_TUNNEL_PRESENT="$(env_value "$CLOUDFLARE_ENV" HIVE_CLOUDFLARE_TUNNEL_TOKEN)"

echo "[6/7] Service activation..."
if [[ "$NO_START" == "1" ]]; then
  echo "START_SKIPPED=true"
elif (( ${#BRIDGE_TOKEN_PRESENT} >= 32 )); then
  systemctl enable --now hive-agent-gateway.service
  systemctl enable --now hive-agent-gateway-health.timer
  echo "BRIDGE_SERVICE_ENABLED=true"
else
  systemctl disable --now hive-agent-gateway.service >/dev/null 2>&1 || true
  systemctl disable --now hive-agent-gateway-health.timer >/dev/null 2>&1 || true
  echo "BRIDGE_SERVICE_ENABLED=false"
  echo "BRIDGE_TOKEN_REQUIRED=true"
fi

if [[ "$NO_START" == "1" ]]; then
  :
elif [[ -n "$CF_TUNNEL_PRESENT" ]]; then
  systemctl enable --now hive-agent-gateway-cloudflared.service
  echo "CLOUDFLARED_SERVICE_ENABLED=true"
else
  echo "CLOUDFLARED_SERVICE_ENABLED=false"
  echo "CLOUDFLARE_TUNNEL_TOKEN_REQUIRED=true"
fi

echo "[7/7] Local verification..."
if systemctl is-active --quiet hive-agent-gateway.service; then
  if "$APP_DIR/ops/agent-gateway/healthcheck.sh"; then
    echo "INSTALL_LOCAL_BRIDGE_PROOF=PASS"
  else
    echo "INSTALL_LOCAL_BRIDGE_PROOF=FAIL" >&2
    exit 9
  fi
else
  echo "INSTALL_LOCAL_BRIDGE_PROOF=PENDING"
fi

if need_cmd tailscale; then
  echo "TAILSCALE_PRESENT=true"
else
  echo "TAILSCALE_PRESENT=false"
  echo "TAILSCALE_ACTION=install_and_enroll_before_remote_admin"
fi

echo "HIVE_AGENT_GATEWAY_PACKAGE=INSTALLED"
echo "SECRETS_EXPOSED=false"
echo "APP_DIR=$APP_DIR"
echo "STATE_DIR=$STATE_DIR"
echo "CONFIG_DIR=$CONFIG_DIR"
