#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d node_modules/playwright ]]; then
  echo "GROK LAB: installazione dipendenze..."
  npm install
fi

bash ./start-browser.sh

export GROK_LAB_CDP_URL="${GROK_LAB_CDP_URL:-http://127.0.0.1:9226}"
node certify-v5.mjs
