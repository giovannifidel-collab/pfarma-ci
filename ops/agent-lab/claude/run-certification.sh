#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

chmod +x start-browser.sh
./start-browser.sh

if [[ ! -d node_modules/playwright-core ]]; then
  npm install
fi

export CLAUDE_LAB_CDP_URL="${CLAUDE_LAB_CDP_URL:-http://127.0.0.1:9224}"
node certify.mjs
