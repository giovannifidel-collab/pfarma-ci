#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

bash ./start-browser.sh
node ./set-deepthink.mjs
node ./certify-deepthink.mjs
