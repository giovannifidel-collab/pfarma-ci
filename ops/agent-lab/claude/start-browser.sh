#!/usr/bin/env bash
set -euo pipefail

PROFILE="${CLAUDE_LAB_PROFILE_DIR:-$HOME/.hive-agent-lab/claude-profile}"
PORT="${CLAUDE_LAB_CDP_PORT:-9224}"
mkdir -p "$PROFILE"

find_browser(){
  for bin in google-chrome-stable google-chrome chromium chromium-browser; do
    if command -v "$bin" >/dev/null 2>&1; then command -v "$bin"; return 0; fi
  done
  return 1
}

BROWSER="${CLAUDE_LAB_BROWSER_BIN:-}"
if [[ -z "$BROWSER" ]]; then BROWSER="$(find_browser || true)"; fi
if [[ -z "$BROWSER" ]]; then
  echo "ERROR: Chrome/Chromium non trovato. Imposta CLAUDE_LAB_BROWSER_BIN oppure installa Chromium nel browser host/Codespace."
  exit 1
fi

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "CLAUDE LAB BROWSER READY"
  echo "CDP=http://127.0.0.1:${PORT}"
  echo "PROFILE=$PROFILE"
  exit 0
fi

export DISPLAY="${DISPLAY:-:1}"
nohup "$BROWSER" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  "https://claude.ai/new" \
  >"$PROFILE/chrome.log" 2>&1 &

echo $! > "$PROFILE/chrome.pid"
for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    echo "CLAUDE LAB BROWSER READY"
    echo "CDP=http://127.0.0.1:${PORT}"
    echo "PROFILE=$PROFILE"
    echo "Apri questo stesso browser via noVNC e accedi a Claude.ai una sola volta."
    exit 0
  fi
  sleep 0.4
done

echo "ERROR: browser avviato ma CDP non raggiungibile. Controlla $PROFILE/chrome.log"
exit 1
