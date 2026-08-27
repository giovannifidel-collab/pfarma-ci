#!/usr/bin/env bash
set -euo pipefail

CFG="$HOME/.openclaw/openclaw.json"
OPENCLAW="$HOME/.local/bin/openclaw"

if [[ ! -f "$CFG" ]]; then
  echo "OpenClaw config not found: $CFG" >&2
  exit 1
fi
if [[ ! -x "$OPENCLAW" ]]; then
  echo "OpenClaw CLI not found: $OPENCLAW" >&2
  exit 1
fi

cp "$CFG" "$CFG.bak-before-kimi-k3"

node - "$CFG" <<'NODE'
const fs = require('fs');
const p = process.argv[2];
const cfg = JSON.parse(fs.readFileSync(p,'utf8'));
const providers = cfg.models && cfg.models.providers;
if (!providers || !providers['kimi-coding']) {
  console.error('kimi-coding provider not found in OpenClaw config. Pairing/plugin is present, but model provider credentials/config were not provisioned.');
  process.exit(2);
}
const prov = providers['kimi-coding'];
prov.models = Array.isArray(prov.models) ? prov.models : [];
if (!prov.models.some(m => m && m.id === 'k3')) {
  prov.models.push({
    id: 'k3',
    name: 'k3',
    input: ['text','image'],
    reasoning: true,
    contextWindow: 1048576,
    maxTokens: 65536
  });
}
cfg.agents = cfg.agents || {};
cfg.agents.defaults = cfg.agents.defaults || {};
cfg.agents.defaults.model = cfg.agents.defaults.model || {};
cfg.agents.defaults.model.primary = 'kimi-coding/k3';
fs.writeFileSync(p, JSON.stringify(cfg, null, 2) + '\n');
console.log('Model switched to kimi-coding/k3');
NODE

"$OPENCLAW" gateway stop >/dev/null 2>&1 || true
sleep 1

# Ensure any residual listener is gone before restarting.
if command -v ss >/dev/null 2>&1; then
  PIDS="$(ss -ltnp '( sport = :18789 )' 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u | tr '\n' ' ')"
  if [[ -n "$PIDS" ]]; then
    kill -TERM $PIDS >/dev/null 2>&1 || true
    sleep 1
  fi
fi

nohup "$OPENCLAW" gateway --bind loopback --port 18789 >/tmp/hive-openclaw-gateway.log 2>&1 &
sleep 4

if ! "$OPENCLAW" gateway status >/dev/null 2>&1; then
  echo "Gateway did not become healthy after Kimi model switch." >&2
  tail -n 100 /tmp/hive-openclaw-gateway.log >&2 || true
  exit 1
fi

echo "KIMI MODEL READY"
echo "Primary model: $($OPENCLAW config get agents.defaults.model.primary 2>/dev/null || true)"
echo "Now test /ping in the linked Kimi/OpenClaw chat."
