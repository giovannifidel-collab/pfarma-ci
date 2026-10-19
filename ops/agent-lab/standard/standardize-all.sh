#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
command -v node >/dev/null 2>&1 || { echo "ERROR: node not found"; exit 1; }

echo "=== HIVE STANDARD LAYER PRECHECK ==="
for f in \
  ./lib/browser-agent.mjs \
  ./lib/keyboard-browser-agent.mjs \
  ./lib/marker-browser-agent.mjs \
  ./lib/kimi-browser-agent.mjs \
  ./lib/kimi-hybrid-agent.mjs \
  ./lib/gemini-browser-agent.mjs \
  ./lib/qwen-browser-agent.mjs \
  ./lib/meta-browser-agent.mjs \
  ./lib/duck-browser-agent.mjs \
  ./agents.mjs \
  ./index.mjs \
  ./standardize-all.mjs \
  ./run-one.mjs \
  ./validate-static.mjs; do
  node --check "$f"
done
node ./validate-static.mjs

echo
node ./standardize-all.mjs "$@"
