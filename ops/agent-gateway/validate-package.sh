#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

required=(
  ops/agent-gateway/README.md
  ops/agent-gateway/install.sh
  ops/agent-gateway/healthcheck.sh
  ops/agent-gateway/migrate-browser-state.sh
  ops/agent-gateway/gateway.env.example
  ops/agent-gateway/cloudflare.env.example
  ops/agent-gateway/systemd/hive-agent-gateway.service
  ops/agent-gateway/systemd/hive-agent-gateway-health.service
  ops/agent-gateway/systemd/hive-agent-gateway-health.timer
  ops/agent-gateway/systemd/hive-agent-gateway-cloudflared.service
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "MISSING=$f" >&2; exit 2; }
done

bash -n ops/agent-gateway/install.sh
bash -n ops/agent-gateway/healthcheck.sh
bash -n ops/agent-gateway/migrate-browser-state.sh
node --check ops/agent-lab/bridge/server.mjs
node --check ops/agent-lab/standard/agents.mjs

# Permanent gateway must bind the bridge locally and must not ship real secrets.
grep -q '^HIVE_AGENT_BRIDGE_HOST=127\.0\.0\.1$' ops/agent-gateway/gateway.env.example
grep -q '^HIVE_AGENT_BRIDGE_TOKEN=$' ops/agent-gateway/gateway.env.example
grep -q '^HIVE_CLOUDFLARE_TUNNEL_TOKEN=$' ops/agent-gateway/cloudflare.env.example

# Ensure production systemd path uses the stable bridge, not the legacy Quick Tunnel wrapper.
grep -q 'ops/agent-lab/bridge/server\.mjs' ops/agent-gateway/systemd/hive-agent-gateway.service
if grep -R -q 'trycloudflare\.com' ops/agent-gateway/systemd; then
  echo 'ERROR: Quick Tunnel reference found in production systemd units.' >&2
  exit 3
fi

echo 'HIVE_AGENT_GATEWAY_PACKAGE_STATIC_VALIDATION=PASS'
echo 'STRICT_10_OF_10_GATE_TOUCHED=false'
echo 'SECRETS_EMBEDDED=false'
