#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

bash ./start-browser.sh

export GROK_LAB_CDP_URL="${GROK_LAB_CDP_URL:-http://127.0.0.1:9226}"

# Atomic certification: every trial contains all required data in one prompt.
# State is resumable so free-tier quota interruptions do not waste completed work.
node certify-v10-atomic.mjs
