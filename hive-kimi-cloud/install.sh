#!/usr/bin/env bash
set -euo pipefail

if ! command -v kimi >/dev/null 2>&1; then
  echo 'Installing Kimi Code CLI using the official Moonshot installer...'
  curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash
fi

# The official installer may place the binary under ~/.local/bin in a fresh shell.
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"

if ! command -v kimi >/dev/null 2>&1; then
  echo 'Kimi Code installation completed but kimi is still not on PATH.' >&2
  echo 'Inspect ~/.local/bin and restart the terminal if needed.' >&2
  exit 1
fi

mkdir -p "$HOME/.kimi-code"
echo "Kimi Code: $(kimi --version)"
echo "HIVE cloud bootstrap environment ready."
echo "Run: bash hive-kimi-cloud/bootstrap-oauth.sh"
