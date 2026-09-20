#!/usr/bin/env bash
set -euo pipefail

BRIDGE_TOKEN_FILE=""
CLOUDFLARE_TOKEN_FILE=""
BROWSER_STATE_DIR=""
POST_REBOOT=0
RUN_LIVE_PROOF=0
SKIP_PACKAGE_VALIDATION=0

usage(){
  cat <<'USAGE'
Usage: sudo bash go-live.sh [options]

Options:
  --token-file PATH             protected file containing the existing stable bridge token
  --cloudflare-token-file PATH  protected file containing the Cloudflare Named Tunnel token
  --browser-state PATH          exported .hive-agent-lab directory to migrate after install
  --post-reboot                 verification mode after a reboot
  --live-proof                  run fresh calls on the 8 currently managed agents
  --skip-package-validation     skip validate-package.sh (normally keep enabled)
  -h, --help                    show this help

This script never prints secret values and never generates or rotates the bridge token.
It does not reboot the machine automatically.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token-file) BRIDGE_TOKEN_FILE="${2:?missing path}"; shift 2 ;;
    --cloudflare-token-file) CLOUDFLARE_TOKEN_FILE="${2:?missing path}"; shift 2 ;;
    --browser-state) BROWSER_STATE_DIR="${2:?missing path}"; shift 2 ;;
    --post-reboot) POST_REBOOT=1; shift ;;
    --live-proof) RUN_LIVE_PROOF=1; shift ;;
    --skip-package-validation) SKIP_PACKAGE_VALIDATION=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || { echo "ERROR: run as root (sudo)." >&2; exit 1; }

APP_DIR="/opt/hive/pfarma-ci"
GATEWAY_DIR="${APP_DIR}/ops/agent-gateway"

bool_cmd(){ command -v "$1" >/dev/null 2>&1; }
service_state(){ systemctl "$1" "$2" 2>/dev/null || true; }

preflight(){
  echo "=== HIVE AGENT GATEWAY GO-LIVE ==="
  echo "PHASE=preflight"
  [[ "$(uname -s)" == "Linux" ]] || { echo "PREFLIGHT_OS=FAIL" >&2; exit 10; }
  bool_cmd systemctl || { echo "PREFLIGHT_SYSTEMD=FAIL" >&2; exit 11; }
  echo "PREFLIGHT_OS=PASS"
  echo "PREFLIGHT_SYSTEMD=PASS"
  echo "PREFLIGHT_ARCH=$(uname -m)"
  echo "PREFLIGHT_RAM_KB=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
  echo "PREFLIGHT_ROOT_FREE_KB=$(df -Pk / | awk 'NR==2 {print $4}')"
  if bool_cmd tailscale; then
    echo "TAILSCALE_PRESENT=true"
  else
    echo "TAILSCALE_PRESENT=false"
  fi
}

network_boundary_proof(){
  local bad=0 listeners
  listeners="$(ss -ltnH 2>/dev/null || true)"

  if printf '%s\n' "$listeners" | awk '$4 ~ /(^|:)9240$/ {print $4}' | grep -Ev '^(127\.0\.0\.1|\[::1\]):9240$' | grep -q .; then
    echo "BRIDGE_BIND_LOCALHOST=FAIL" >&2
    bad=1
  elif printf '%s\n' "$listeners" | awk '$4 ~ /(^|:)9240$/ {found=1} END {exit !found}'; then
    echo "BRIDGE_BIND_LOCALHOST=PASS"
  else
    echo "BRIDGE_BIND_LOCALHOST=NOT_LISTENING" >&2
    bad=1
  fi

  if printf '%s\n' "$listeners" | awk '$4 ~ /(^|:)(922[0-9]|923[0-9])$/ {print $4}' | grep -Ev '^(127\.0\.0\.1|\[::1\]):(922[0-9]|923[0-9])$' | grep -q .; then
    echo "CDP_BIND_LOCALHOST=FAIL" >&2
    bad=1
  else
    echo "CDP_BIND_LOCALHOST=PASS"
  fi

  (( bad == 0 ))
}

service_proof(){
  local bridge_active health_active bridge_enabled health_enabled tunnel_active tunnel_enabled
  bridge_active="$(service_state is-active hive-agent-gateway.service)"
  health_active="$(service_state is-active hive-agent-gateway-health.timer)"
  bridge_enabled="$(service_state is-enabled hive-agent-gateway.service)"
  health_enabled="$(service_state is-enabled hive-agent-gateway-health.timer)"
  tunnel_active="$(service_state is-active hive-agent-gateway-cloudflared.service)"
  tunnel_enabled="$(service_state is-enabled hive-agent-gateway-cloudflared.service)"

  echo "BRIDGE_SERVICE_ACTIVE=${bridge_active:-unknown}"
  echo "HEALTH_TIMER_ACTIVE=${health_active:-unknown}"
  echo "BRIDGE_SERVICE_ENABLED=${bridge_enabled:-unknown}"
  echo "HEALTH_TIMER_ENABLED=${health_enabled:-unknown}"
  echo "TUNNEL_SERVICE_ACTIVE=${tunnel_active:-unknown}"
  echo "TUNNEL_SERVICE_ENABLED=${tunnel_enabled:-unknown}"

  [[ "$bridge_active" == "active" && "$health_active" == "active" && "$bridge_enabled" == "enabled" && "$health_enabled" == "enabled" ]]
}

runtime_proof(){
  [[ -x "$GATEWAY_DIR/healthcheck.sh" ]] || chmod +x "$GATEWAY_DIR/healthcheck.sh"
  "$GATEWAY_DIR/healthcheck.sh"
  network_boundary_proof
  service_proof
}

preflight

if [[ "$POST_REBOOT" == "1" ]]; then
  [[ -d "$APP_DIR/.git" ]] || { echo "POST_REBOOT_CHECKOUT=NOT_FOUND" >&2; exit 20; }
  echo "PHASE=post_reboot_proof"
  runtime_proof
  echo "BRIDGE_AUTOSTART=PASS"
  echo "HIVE_AGENT_GATEWAY_POST_REBOOT=PASS"
  if [[ "$RUN_LIVE_PROOF" == "1" ]]; then
    echo "PHASE=managed_agent_live_proof"
    bash "$GATEWAY_DIR/live-proof-managed.sh"
    echo "HIVE_AGENT_GATEWAY=READY_PENDING_TUNNEL_PUBLIC_PROOF_IF_NOT_CONFIGURED"
  else
    echo "NEXT=run_managed_agent_live_proof_8_of_8"
  fi
  exit 0
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SKIP_PACKAGE_VALIDATION" != "1" ]]; then
  echo "PHASE=package_validation"
  bash "$SCRIPT_DIR/validate-package.sh"
fi

args=()
if [[ -n "$BRIDGE_TOKEN_FILE" ]]; then
  [[ -f "$BRIDGE_TOKEN_FILE" ]] || { echo "ERROR: bridge token file not found." >&2; exit 30; }
  args+=(--token-file "$BRIDGE_TOKEN_FILE")
fi
if [[ -n "$CLOUDFLARE_TOKEN_FILE" ]]; then
  [[ -f "$CLOUDFLARE_TOKEN_FILE" ]] || { echo "ERROR: Cloudflare tunnel token file not found." >&2; exit 31; }
  args+=(--cloudflare-token-file "$CLOUDFLARE_TOKEN_FILE")
fi

echo "PHASE=install"
bash "$SCRIPT_DIR/install.sh" "${args[@]}"

if [[ -n "$BROWSER_STATE_DIR" ]]; then
  [[ -d "$BROWSER_STATE_DIR" ]] || { echo "ERROR: browser-state directory not found." >&2; exit 32; }
  echo "PHASE=browser_state_migration"
  bash "$GATEWAY_DIR/migrate-browser-state.sh" "$BROWSER_STATE_DIR"
fi

echo "PHASE=runtime_proof"
runtime_proof

echo "HIVE_AGENT_GATEWAY_PRE_REBOOT=PASS"
echo "CODESPACE_DEPENDENCY=READY_TO_REMOVE_AFTER_REBOOT_AND_8_OF_8_PROOF"
echo "REBOOT_PROOF_REQUIRED=true"
echo "NEXT_COMMAND=sudo reboot"
echo "AFTER_REBOOT_COMMAND=sudo bash /opt/hive/pfarma-ci/ops/agent-gateway/go-live.sh --post-reboot --live-proof"
