#!/usr/bin/env bash
set -euo pipefail

if ! command -v kimi >/dev/null 2>&1; then
  npm install -g @moonshot-ai/kimi-code@latest
fi

mkdir -p "$HOME/.kimi-code"
echo "Kimi Code: $(kimi --version)"
echo "HIVE cloud bootstrap environment ready."
echo "Run: bash hive-kimi-cloud/bootstrap-oauth.sh"
