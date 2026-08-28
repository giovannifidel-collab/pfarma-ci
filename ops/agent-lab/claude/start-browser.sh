#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROFILE="${CLAUDE_LAB_PROFILE_DIR:-$HOME/.hive-agent-lab/claude-profile}"
PORT="${CLAUDE_LAB_CDP_PORT:-9224}"
DISK_CACHE_BYTES="${CLAUDE_LAB_DISK_CACHE_BYTES:-134217728}"
MEDIA_CACHE_BYTES="${CLAUDE_LAB_MEDIA_CACHE_BYTES:-33554432}"
mkdir -p "$PROFILE"

playwright_browser(){
  [[ -d node_modules/playwright ]] || return 1
  local candidate
  candidate="$(node --input-type=module -e "import { chromium } from 'playwright'; process.stdout.write(chromium.executablePath())" 2>/dev/null || true)"
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  return 1
}

find_browser(){
  if [[ -n "${CLAUDE_LAB_BROWSER_BIN:-}" && -x "${CLAUDE_LAB_BROWSER_BIN}" ]]; then
    printf '%s\n' "$CLAUDE_LAB_BROWSER_BIN"
    return 0
  fi

  for bin in google-chrome-stable google-chrome chromium chromium-browser; do
    if command -v "$bin" >/dev/null 2>&1; then
      command -v "$bin"
      return 0
    fi
  done

  playwright_browser && return 0
  return 1
}

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "CLAUDE LAB BROWSER READY"
  echo "CDP=http://127.0.0.1:${PORT}"
  echo "PROFILE=$PROFILE"
  exit 0
fi

if [[ ! -d node_modules/playwright ]]; then
  echo "CLAUDE LAB: installazione dipendenze Node..."
  npm install
fi

BROWSER="$(find_browser || true)"
if [[ -z "$BROWSER" ]]; then
  echo "CLAUDE LAB: Chromium non presente; download Playwright Chromium..."
  npx playwright install chromium
  BROWSER="$(find_browser || true)"
fi

if [[ -z "$BROWSER" ]]; then
  echo "ERROR: Chromium non disponibile anche dopo il bootstrap Playwright."
  echo "Prova: npx playwright install --with-deps chromium"
  exit 1
fi

echo "CLAUDE LAB BROWSER=$BROWSER"

export DISPLAY="${DISPLAY:-:1}"
DISPLAY_NUM="${DISPLAY#:}"
DISPLAY_NUM="${DISPLAY_NUM%%.*}"
if [[ "$DISPLAY" == :* && ! -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
  echo "ERROR: display grafico $DISPLAY non attivo nel Codespace."
  echo "Chromium e' installato correttamente; manca solo la sessione X/noVNC."
  echo "DISPLAY=$DISPLAY"
  exit 3
fi

# Preserve authentication/session state, but remove disposable Chromium caches.
# This keeps the Claude login while preventing cache directories from growing indefinitely.
rm -rf \
  "$PROFILE/Default/Cache" \
  "$PROFILE/Default/Code Cache" \
  "$PROFILE/Default/GPUCache" \
  "$PROFILE/ShaderCache" \
  "$PROFILE/GrShaderCache" \
  2>/dev/null || true

nohup "$BROWSER" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --disk-cache-size="$DISK_CACHE_BYTES" \
  --media-cache-size="$MEDIA_CACHE_BYTES" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --no-sandbox \
  "https://claude.ai/new" \
  >"$PROFILE/chrome.log" 2>&1 &

echo $! > "$PROFILE/chrome.pid"
for _ in $(seq 1 75); do
  if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    echo "CLAUDE LAB BROWSER READY"
    echo "CDP=http://127.0.0.1:${PORT}"
    echo "PROFILE=$PROFILE"
    echo "CACHE_CAP=$((DISK_CACHE_BYTES/1024/1024))MiB disk + $((MEDIA_CACHE_BYTES/1024/1024))MiB media"
    echo "Accedi a Claude.ai dalla finestra Chromium del noVNC; le credenziali restano nel browser."
    exit 0
  fi
  sleep 0.4
done

echo "ERROR: Chromium avviato ma CDP non raggiungibile."
echo "----- chrome.log -----"
tail -n 40 "$PROFILE/chrome.log" 2>/dev/null || true
exit 1
