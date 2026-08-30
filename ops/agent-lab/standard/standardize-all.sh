#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
command -v node >/dev/null 2>&1 || { echo "ERROR: node not found"; exit 1; }
node ./standardize-all.mjs "$@"
