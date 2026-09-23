#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d node_modules/playwright ]]; then
  echo "GEMINI LAB: installazione dipendenze..."
  npm install
fi

bash ./start-browser.sh

export GEMINI_LAB_CDP_URL="${GEMINI_LAB_CDP_URL:-http://127.0.0.1:9225}"
node certify.mjs
