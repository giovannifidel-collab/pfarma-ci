#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_VERSION="2026.4.2"
PREFIX="$HOME/.openclaw"
BIN="$PREFIX/bin/openclaw"
LOCAL_BIN="$HOME/.local/bin"
LOG="/tmp/hive-openclaw-gateway.log"

echo "=== HIVE OPENCLAW CLOUD BOOTSTRAP ==="
echo "Target OpenClaw version: $OPENCLAW_VERSION"
echo "Install prefix: $PREFIX"

mkdir -p "$LOCAL_BIN"
export PATH="$LOCAL_BIN:$PREFIX/bin:$PATH"

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

if [[ ! -x "$BIN" ]]; then
  echo "OpenClaw binary not found at $BIN" >&2
  exit 1
fi

# Kimi's pairing installer discovers dependencies with `command -v`.
ln -sfn "$BIN" "$LOCAL_BIN/openclaw"

# OpenClaw managed/user-space installs keep an embedded Node runtime under
# ~/.openclaw/tools/node-v*/bin. The `node` entry may itself be a symlink, so
# resolve candidates via shell globbing rather than `find -type f`.
NODE_BIN_DIR=""
NODE_CANDIDATES=()
for candidate in "$PREFIX"/tools/node-v*/bin/node; do
  [[ -e "$candidate" || -L "$candidate" ]] || continue
  [[ -x "$candidate" ]] || continue
  NODE_CANDIDATES+=("$(dirname "$candidate")")
done

if (( ${#NODE_CANDIDATES[@]} > 0 )); then
  NODE_BIN_DIR="$(printf '%s\n' "${NODE_CANDIDATES[@]}" | sort -V | tail -n 1)"
fi

if [[ -z "$NODE_BIN_DIR" || ! -x "$NODE_BIN_DIR/node" ]]; then
  echo "Embedded OpenClaw Node runtime was not found under $PREFIX/tools." >&2
  echo "Diagnostic tree:" >&2
  find "$PREFIX/tools" -maxdepth 3 \( -type f -o -type l \) -print 2>/dev/null | head -n 120 >&2 || true
  exit 1
fi

echo "Embedded Node runtime: $NODE_BIN_DIR"

for tool in node npm npx; do
  if [[ ! -e "$NODE_BIN_DIR/$tool" && ! -L "$NODE_BIN_DIR/$tool" ]]; then
    echo "Embedded runtime is missing required tool: $NODE_BIN_DIR/$tool" >&2
    ls -la "$NODE_BIN_DIR" >&2 || true
    exit 1
  fi
  rm -f "$LOCAL_BIN/$tool"
  ln -s "$NODE_BIN_DIR/$tool" "$LOCAL_BIN/$tool"
done

# Put the real runtime directory first; ~/.local/bin aliases are retained for
# fresh shells and Kimi's installer subprocesses.
export PATH="$NODE_BIN_DIR:$LOCAL_BIN:$PREFIX/bin:$PATH"
hash -r

PATH_LINE='export PATH="$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"'
if ! grep -Fq "$PATH_LINE" "$HOME/.bashrc" 2>/dev/null; then
  printf '\n%s\n' "$PATH_LINE" >> "$HOME/.bashrc"
fi

printf 'OpenClaw: '
openclaw --version
printf 'OpenClaw path: '
command -v openclaw

for tool in node npm npx; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Required Node tool missing after embedded-runtime activation: $tool" >&2
    exit 1
  fi
  printf '%s path: ' "$tool"
  command -v "$tool"
  "$tool" --version | head -n 1
done

# Minimal loopback-only gateway configuration. No model/API provider is configured here.
openclaw config set gateway.mode local >/dev/null
openclaw config set gateway.bind loopback >/dev/null || true
openclaw config set gateway.auth.mode token >/dev/null

if ! openclaw config get gateway.auth.token >/dev/null 2>&1; then
  TOKEN="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
  openclaw config set gateway.auth.token "$TOKEN" >/dev/null
fi

# Codespaces do not need a persistent system daemon for this certification.
pkill -f 'openclaw gateway' >/dev/null 2>&1 || true
nohup openclaw gateway --bind loopback --port 18789 >"$LOG" 2>&1 &
GW_PID=$!

for _ in {1..30}; do
  if openclaw gateway status >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! openclaw gateway status >/dev/null 2>&1; then
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
