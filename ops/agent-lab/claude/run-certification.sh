#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d node_modules/playwright ]]; then
  echo "CLAUDE LAB: installazione dipendenze..."
  npm install
fi

bash ./start-browser.sh

export CLAUDE_LAB_CDP_URL="${CLAUDE_LAB_CDP_URL:-http://127.0.0.1:9224}"
node certify.mjs
