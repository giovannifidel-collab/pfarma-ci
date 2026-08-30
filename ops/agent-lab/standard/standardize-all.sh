#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
command -v node >/dev/null 2>&1 || { echo "ERROR: node not found"; exit 1; }

echo "=== HIVE STANDARD LAYER PRECHECK ==="
node --check ./lib/browser-agent.mjs
node --check ./agents.mjs
node --check ./index.mjs
node --check ./standardize-all.mjs
node --check ./run-one.mjs
node --check ./validate-static.mjs
node ./validate-static.mjs

echo
node ./standardize-all.mjs "$@"
