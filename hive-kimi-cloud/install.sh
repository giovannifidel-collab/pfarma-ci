#!/usr/bin/env bash
set -euo pipefail

if ! command -v kimi >/dev/null 2>&1; then
  echo 'Installing Kimi Code CLI using the official GLOBAL Moonshot installer...'
  curl -fsSL https://code.kimi.ai/kimi-code/install.sh | bash
fi

# Official installers currently place the binary under ~/.kimi-code/bin.
export PATH="$HOME/.kimi-code/bin:$HOME/.local/bin:$HOME/bin:$PATH"

if ! command -v kimi >/dev/null 2>&1; then
  echo 'Kimi Code installation completed but kimi is still not on PATH.' >&2
  echo 'Run: source ~/.bashrc' >&2
  exit 1
fi

mkdir -p "$HOME/.kimi-code"
printf 'global\n' > "$HOME/.kimi-code/region"

echo "Kimi Code: $(kimi --version)"
echo 'Kimi region: global (.ai)'
echo 'HIVE cloud bootstrap environment ready.'
echo 'Run: bash hive-kimi-cloud/bootstrap-oauth.sh'
