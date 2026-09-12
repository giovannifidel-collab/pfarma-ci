#!/usr/bin/env bash
set -euo pipefail

PREFIX="$HOME/.openclaw"
LOCAL_BIN="$HOME/.local/bin"
NODE_BIN_DIR="$(for d in "$PREFIX"/tools/node-v*/bin; do [[ -x "$d/node" ]] && printf '%s\n' "$d"; done | sort -V | tail -n 1)"

if [[ -z "$NODE_BIN_DIR" ]]; then
  echo "NODE_RUNTIME_NOT_FOUND"
  exit 1
fi

export PATH="$NODE_BIN_DIR:$LOCAL_BIN:$PREFIX/bin:$PATH"
OPENCLAW_PKG="$NODE_BIN_DIR/../lib/node_modules/openclaw"

printf '=== HIVE KIMI RUNTIME DIAGNOSTIC ===\n'
printf 'node=%s\n' "$(command -v node || true)"
printf 'node_version=%s\n' "$(node --version 2>/dev/null || true)"
printf 'openclaw=%s\n' "$(command -v openclaw || true)"
printf 'openclaw_real=%s\n' "$(readlink -f "$(command -v openclaw)" 2>/dev/null || true)"
printf 'openclaw_version=%s\n' "$(openclaw --version 2>/dev/null || true)"
printf 'package_root=%s\n' "$OPENCLAW_PKG"

printf '\n=== GRAMMY RESOLUTION ===\n'
if [[ -e "$OPENCLAW_PKG/node_modules/grammy/package.json" ]]; then
  echo "package_local_grammy=present"
else
  echo "package_local_grammy=missing"
fi

(
  cd "$OPENCLAW_PKG"
  node --input-type=module -e "import('grammy').then(m=>console.log('cwd_import=ok')).catch(e=>{console.log('cwd_import=FAIL '+e.message);process.exitCode=1})"
) || true

(
  cd "$OPENCLAW_PKG/dist"
  node --input-type=module -e "import('grammy').then(m=>console.log('dist_import=ok')).catch(e=>{console.log('dist_import=FAIL '+e.message);process.exitCode=1})"
) || true

STICKER="$(find "$OPENCLAW_PKG/dist" -maxdepth 1 -type f -name 'sticker-cache-*.js' -print -quit 2>/dev/null || true)"
if [[ -n "$STICKER" ]]; then
  printf 'sticker_module=%s\n' "$STICKER"
else
  echo 'sticker_module=not_found'
fi

printf '\n=== PROCESSES ===\n'
ps -eo pid,ppid,lstart,args | grep -E '[o]penclaw|[k]imiim' | sed -E 's/(--bot-token)[= ]+[^ ]+/\1 REDACTED/g' || true

printf '\n=== GATEWAY STATUS ===\n'
openclaw gateway status 2>&1 || true

printf '\n=== KIMI PLUGIN CONFIG PRESENCE ===\n'
if openclaw config get plugins.entries.kimi-claw >/dev/null 2>&1; then
  echo 'kimi_plugin_config=present'
else
  echo 'kimi_plugin_config=missing'
fi

printf '\n=== GATEWAY LOG TAIL ===\n'
tail -n 160 /tmp/hive-openclaw-gateway.log 2>/dev/null | sed -E 's/(km_b_[A-Za-z0-9_\-]+)/REDACTED_TOKEN/g' || echo 'gateway_log=missing'

printf '\n=== END DIAGNOSTIC ===\n'
