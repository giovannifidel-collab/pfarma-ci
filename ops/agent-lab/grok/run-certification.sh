#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

bash ./start-browser.sh

export GROK_LAB_CDP_URL="${GROK_LAB_CDP_URL:-http://127.0.0.1:9226}"

# Grok certification uses page-level Chrome DevTools Protocol directly and
# persists checkpoints so free-tier quota interruptions can resume cleanly.
node certify-v9-resumable.mjs
