#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_VERSION="2026.4.2"
PREFIX="$HOME/.openclaw"
BIN="$PREFIX/bin/openclaw"
LOG="/tmp/hive-openclaw-gateway.log"

echo "=== HIVE OPENCLAW CLOUD BOOTSTRAP ==="
echo "Target OpenClaw version: $OPENCLAW_VERSION"
echo "Install prefix: $PREFIX"

export PATH="$PREFIX/bin:$PATH"

CURRENT_VERSION=""
if [[ -x "$BIN" ]]; then
  CURRENT_VERSION="$($BIN --version 2>/dev/null || true)"
fi

if [[ "$CURRENT_VERSION" != *"$OPENCLAW_VERSION"* ]]; then
  echo "Installing a Kimi-compatible OpenClaw release in the GitHub Codespace..."
  curl -fsSL --proto '=https' --tlsv1.2 https://openclaw.ai/install-cli.sh | \
    bash -s -- --prefix "$PREFIX" --version "$OPENCLAW_VERSION"
else
  echo "OpenClaw $OPENCLAW_VERSION already installed; skipping reinstall."
fi

if ! grep -Fq 'export PATH="$HOME/.openclaw/bin:$PATH"' "$HOME/.bashrc" 2>/dev/null; then
  printf '\nexport PATH="$HOME/.openclaw/bin:$PATH"\n' >> "$HOME/.bashrc"
fi

if [[ ! -x "$BIN" ]]; then
  echo "OpenClaw binary not found at $BIN" >&2
  exit 1
fi

printf 'OpenClaw: '
"$BIN" --version

# Minimal loopback-only gateway configuration. No model/API provider is configured here.
"$BIN" config set gateway.mode local >/dev/null
"$BIN" config set gateway.bind loopback >/dev/null || true
"$BIN" config set gateway.auth.mode token >/dev/null

if ! "$BIN" config get gateway.auth.token >/dev/null 2>&1; then
  if command -v node >/dev/null 2>&1; then
    TOKEN="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
  elif command -v openssl >/dev/null 2>&1; then
    TOKEN="$(openssl rand -hex 32)"
  else
    echo "Neither node nor openssl is available to generate a secure gateway token." >&2
    exit 1
  fi
  "$BIN" config set gateway.auth.token "$TOKEN" >/dev/null
fi

# Codespaces do not need a persistent system daemon for this certification.
pkill -f 'openclaw gateway' >/dev/null 2>&1 || true
nohup "$BIN" gateway --bind loopback --port 18789 >"$LOG" 2>&1 &
GW_PID=$!

for _ in {1..30}; do
  if "$BIN" gateway status >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! "$BIN" gateway status >/dev/null 2>&1; then
  echo "Gateway did not become healthy. Last log lines:" >&2
  tail -n 80 "$LOG" >&2 || true
  exit 1
fi

echo
echo "OPENCLAW READY FOR KIMI PAIRING"
echo "Gateway: ws://127.0.0.1:18789"
echo "PID: $GW_PID"
echo "Log: $LOG"
echo
echo "NEXT: reopen 'Link existing OpenClaw' in Kimi to generate a FRESH pairing token,"
echo "then paste Kimi's generated pairing command directly into this Codespace terminal."
echo "Do not paste or screenshot that token in chat."
