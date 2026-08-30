#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

bash ./start-browser.sh

export GROK_LAB_CDP_URL="${GROK_LAB_CDP_URL:-http://127.0.0.1:9226}"

# Grok certification uses the page-level Chrome DevTools Protocol directly.
# This avoids chromium.connectOverCDP(), which can hang while attaching the
# persistent browser context even when Chrome's debugging WebSocket is healthy.
node certify-v8-direct.mjs
